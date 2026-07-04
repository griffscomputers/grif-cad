#!/usr/bin/env bash
# stack.sh — one-command control for the grif-cad web assistant.
# Three layers, started bottom-up:
#   1. Colima            — the docker engine
#   2. Open WebUI        — browser chat container on :3000
#   3. bridge            — headless Claude Code + OpenSCAD, detached, on :PORT (default 8765)
#
# Unlike start.sh's old foreground bridge, this detaches the bridge (nohup) so it
# survives closing the terminal — no Claude session, no open window required.
#
# Usage:
#   scripts/stack.sh start         bring the whole stack up (idempotent)
#   scripts/stack.sh stop          stop the bridge + web UI (leaves the docker engine)
#   scripts/stack.sh restart       bounce the bridge, ensure web UI/engine are up
#   scripts/stack.sh status        one-line health of each layer
#   scripts/stack.sh check [--deep]  PASS/FAIL test of every layer; exit 1 on any failure
#   scripts/stack.sh logs [-f]     show the bridge log (-f to follow)
#   scripts/stack.sh down [--colima]  full teardown (remove container; --colima stops the engine too)
set -uo pipefail

proj="$(cd "$(dirname "$0")/.." && pwd)"
cd "$proj"

COMPOSE_FILE="deploy/docker-compose.yml"
CONTAINER="grifcad-openwebui"
WEB_PORT=3000
RUN_DIR="$proj/.run"
PIDFILE="$RUN_DIR/bridge.pid"
LOGFILE="$RUN_DIR/bridge.log"

# Bridge port comes from config/bridge.env (PORT=), default 8765.
PORT="$(grep -E '^PORT=' config/bridge.env 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '[:space:]' || true)"
PORT="${PORT:-8765}"
HEALTH="http://127.0.0.1:$PORT/healthz"
MODELS="http://127.0.0.1:$PORT/v1/models"

mkdir -p "$RUN_DIR"

if [ -t 1 ]; then G=$'\e[32m'; R=$'\e[31m'; Y=$'\e[33m'; B=$'\e[1m'; N=$'\e[0m'; else G=; R=; Y=; B=; N=; fi
info(){ echo "${B}==>${N} $*"; }
ok(){   echo "  ${G}OK${N}  $*"; }
bad(){  echo "  ${R}!!${N}  $*"; }

http_code(){ curl -s -m "${2:-3}" -o /dev/null -w '%{http_code}' "$1" 2>/dev/null || true; }
bridge_healthy(){ curl -s -m 3 "$HEALTH" 2>/dev/null | grep -q '"ok":true'; }
bridge_pid(){ lsof -ti tcp:"$PORT" -sTCP:LISTEN 2>/dev/null | head -1; }

# ---- layer bring-up ---------------------------------------------------------

ensure_colima(){
  if colima status >/dev/null 2>&1; then ok "colima already running"
  else info "starting colima (docker engine)…"; colima start; fi
  local i
  for i in $(seq 1 30); do docker info >/dev/null 2>&1 && return 0; sleep 1; done
  bad "docker engine not reachable after 30s"; return 1
}

ensure_webui(){
  info "ensuring Open WebUI container…"
  docker compose -f "$COMPOSE_FILE" up -d || { bad "docker compose up failed"; return 1; }
  local i s
  for i in $(seq 1 60); do
    s="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$CONTAINER" 2>/dev/null || true)"
    [ "$s" = healthy ] && { ok "Open WebUI healthy (:$WEB_PORT)"; return 0; }
    sleep 1
  done
  [ "$(http_code "http://127.0.0.1:$WEB_PORT" 5)" = 200 ] && { ok "Open WebUI responding (:$WEB_PORT)"; return 0; }
  bad "Open WebUI did not come up"; return 1
}

start_bridge(){
  if bridge_healthy; then ok "bridge already healthy (:$PORT)"; return 0; fi
  local existing; existing="$(bridge_pid)"
  if [ -n "$existing" ]; then
    info "clearing stale listener on :$PORT (pid $existing)…"; kill "$existing" 2>/dev/null || true; sleep 1
  fi
  info "starting bridge, detached (:$PORT)…"
  echo "----- $(date '+%Y-%m-%d %H:%M:%S') stack.sh start -----" >>"$LOGFILE"
  nohup bash bridge/run.sh </dev/null >>"$LOGFILE" 2>&1 &
  echo $! >"$PIDFILE"
  disown 2>/dev/null || true
  local i
  for i in $(seq 1 40); do
    bridge_healthy && { ok "bridge healthy (:$PORT, pid $(cat "$PIDFILE"))"; return 0; }
    sleep 1
  done
  bad "bridge did not become healthy in 40s — run: scripts/stack.sh logs"; return 1
}

stop_bridge(){
  local pid; pid="$(bridge_pid)"; [ -z "$pid" ] && pid="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    info "stopping bridge (pid $pid)…"
    kill "$pid" 2>/dev/null || true
    local i; for i in $(seq 1 10); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
    kill -9 "$pid" 2>/dev/null || true
    ok "bridge stopped"
  else ok "bridge not running"; fi
  rm -f "$PIDFILE"
}

# ---- commands ---------------------------------------------------------------

cmd_start(){
  ensure_colima || return 1
  ensure_webui  || return 1
  start_bridge  || return 1
  echo
  info "Open the assistant:  ${B}http://localhost:$WEB_PORT${N}   (pick the 'grif-cad' model)"
  info "Verify any time:     scripts/stack.sh check"
}

cmd_stop(){
  stop_bridge
  info "stopping Open WebUI container…"
  docker compose -f "$COMPOSE_FILE" stop >/dev/null 2>&1 && ok "Open WebUI stopped" || bad "could not stop container"
  echo
  info "docker engine left running (stop it with: colima stop)"
}

cmd_restart(){
  info "restarting the stack…"
  stop_bridge
  ensure_colima || return 1
  ensure_webui  || return 1
  start_bridge  || return 1
  echo; ok "stack restarted — http://localhost:$WEB_PORT"
}

cmd_down(){
  stop_bridge
  info "removing Open WebUI container…"
  docker compose -f "$COMPOSE_FILE" down >/dev/null 2>&1 && ok "container removed (data volume kept)" || bad "compose down failed"
  if [ "${1:-}" = "--colima" ]; then
    info "stopping docker engine…"; colima stop && ok "colima stopped"
  else
    info "docker engine left running (add --colima to stop it too)"
  fi
}

cmd_status(){
  local bp; bp="$(bridge_pid)"
  echo "${B}grif-cad stack${N}"
  colima status >/dev/null 2>&1 && echo "  colima      ${G}running${N}" || echo "  colima      ${R}stopped${N}"
  local cs; cs="$(docker inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo absent)"
  echo "  web ui      ${cs} (:$WEB_PORT)"
  if [ -n "$bp" ] && bridge_healthy; then echo "  bridge      ${G}healthy${N} (:$PORT, pid $bp)"
  elif [ -n "$bp" ]; then echo "  bridge      ${Y}listening but unhealthy${N} (:$PORT, pid $bp)"
  else echo "  bridge      ${R}down${N} (:$PORT)"; fi
}

cmd_check(){
  local deep=0; [ "${1:-}" = "--deep" ] && deep=1
  local fail=0
  echo "${B}grif-cad stack check${N}  (web :$WEB_PORT, bridge :$PORT)"

  if colima status >/dev/null 2>&1; then ok "colima running"; else bad "colima not running"; fail=$((fail+1)); fi
  if docker info >/dev/null 2>&1; then ok "docker engine reachable"; else bad "docker engine unreachable"; fail=$((fail+1)); fi

  local cs hs
  cs="$(docker inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null || true)"
  hs="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$CONTAINER" 2>/dev/null || true)"
  if [ "$cs" = running ]; then ok "container $CONTAINER running${hs:+ ($hs)}"; else bad "container $CONTAINER not running (state: ${cs:-absent})"; fail=$((fail+1)); fi

  local c; c="$(http_code "http://127.0.0.1:$WEB_PORT" 5)"
  if [ "$c" = 200 ]; then ok "Open WebUI HTTP 200 (:$WEB_PORT)"; else bad "Open WebUI HTTP ${c:-none} (:$WEB_PORT)"; fail=$((fail+1)); fi

  local bp; bp="$(bridge_pid)"
  if [ -n "$bp" ]; then ok "bridge listening (:$PORT, pid $bp)"; else bad "nothing listening on :$PORT"; fail=$((fail+1)); fi

  local hz; hz="$(curl -s -m 5 "$HEALTH" 2>/dev/null || true)"
  if echo "$hz" | grep -q '"ok":true'; then ok "bridge /healthz ok ${hz//[[:space:]]/}"; else bad "bridge /healthz failed"; fail=$((fail+1)); fi

  if curl -s -m 5 "$MODELS" 2>/dev/null | grep -q '"grif-cad"'; then ok "bridge advertises grif-cad model"; else bad "grif-cad model not advertised"; fail=$((fail+1)); fi

  if curl -s -m 5 "$MODELS" 2>/dev/null | grep -q '"grif-cad-text-to-3d"'; then ok "bridge advertises studio modes"; else bad "studio modes not advertised (text-to-3d missing)"; fail=$((fail+1)); fi

  c="$(http_code "http://127.0.0.1:$PORT/studio" 5)"
  if [ "$c" = 200 ]; then ok "studio page HTTP 200 (:$PORT/studio)"; else bad "studio page HTTP ${c:-none}"; fail=$((fail+1)); fi

  if curl -s -m 5 "http://127.0.0.1:$WEB_PORT/static/custom.css" 2>/dev/null | grep -q GrifCAD; then ok "GrifCAD skin served (custom.css)"; else bad "custom.css not served (skin mount missing?)"; fail=$((fail+1)); fi

  if docker exec "$CONTAINER" sh -c \
        "curl -s -m 5 http://host.docker.internal:$PORT/v1/models 2>/dev/null || wget -qO- http://host.docker.internal:$PORT/v1/models 2>/dev/null" \
        2>/dev/null | grep -q '"grif-cad"'; then
    ok "container → bridge wiring OK (host.docker.internal:$PORT)"
  else bad "container cannot reach bridge over host.docker.internal:$PORT"; fail=$((fail+1)); fi

  if [ "$deep" = 1 ]; then
    info "deep: real chat round-trip (invokes Claude — may take ~30-60s)…"
    local body resp
    body='{"model":"grif-cad","stream":false,"messages":[{"role":"user","content":"Reply with the single word READY and nothing else."}]}'
    resp="$(curl -s -m 180 -H 'Content-Type: application/json' -d "$body" "http://127.0.0.1:$PORT/v1/chat/completions" 2>/dev/null || true)"
    if echo "$resp" | "$proj/.venv/bin/python" -c \
        'import sys,json;d=json.load(sys.stdin);c=d["choices"][0]["message"]["content"];print(c.strip()[:60]);sys.exit(0 if c.strip() else 1)' \
        >/tmp/grifcad_deep 2>/dev/null; then
      ok "chat round-trip OK → \"$(cat /tmp/grifcad_deep)\""
    else bad "chat round-trip failed (see: scripts/stack.sh logs)"; fail=$((fail+1)); fi
  fi

  echo
  if [ "$fail" = 0 ]; then echo "${G}${B}ALL CHECKS PASSED${N}"; return 0
  else echo "${R}${B}$fail CHECK(S) FAILED${N}"; return 1; fi
}

cmd_logs(){
  [ -f "$LOGFILE" ] || { echo "no bridge log yet ($LOGFILE)"; return 0; }
  if [ "${1:-}" = "-f" ]; then tail -n 80 -f "$LOGFILE"; else tail -n 80 "$LOGFILE"; fi
}

usage(){ sed -n '2,20p' "$0"; }

case "${1:-}" in
  start)   cmd_start ;;
  stop)    cmd_stop ;;
  restart) cmd_restart ;;
  status)  cmd_status ;;
  check)   shift; cmd_check "${1:-}" ;;
  logs)    shift; cmd_logs "${1:-}" ;;
  down)    shift; cmd_down "${1:-}" ;;
  ""|-h|--help|help) usage ;;
  *) echo "unknown command: $1"; echo; usage; exit 2 ;;
esac
