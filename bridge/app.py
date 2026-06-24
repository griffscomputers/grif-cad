#!/usr/bin/env python3
"""grif-cad bridge — an OpenAI-compatible HTTP front end over headless Claude Code.

    Open WebUI (OpenAI client)  ->  this bridge  ->  `claude -p` in the grif-cad
    project  ->  the full harness (skills, render.sh, the print safety gate).

Rendered preview PNGs the harness produces are served back over HTTP and attached
to the reply as inline images, so they show up in the chat.

Auth: rides the logged-in Claude subscription via CLAUDE_CODE_OAUTH_TOKEN. We
explicitly drop ANTHROPIC_API_KEY so there is no metered API billing.

Safety: claude runs with --permission-mode acceptEdits and an explicit --allowedTools
allowlist that covers modelling/rendering/slicing but NOT the printer step
(print.sh / Moonraker). The physical-print gate stays human-only, even via the web UI.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# ---------------------------------------------------------------- config
PROJECT_DIR = Path(os.environ.get("PROJECT_DIR", Path(__file__).resolve().parent.parent))
PREVIEW_DIR = PROJECT_DIR / "out" / "preview"
SCAD_DIR = PROJECT_DIR / "models" / "openscad"
PORT = int(os.environ.get("PORT", "8765"))
PUBLIC_BASE = os.environ.get("PUBLIC_BASE", f"http://localhost:{PORT}").rstrip("/")
MODEL = os.environ.get("GRIFCAD_MODEL", "sonnet")          # base model (normal requests)
MODEL_MAX = os.environ.get("GRIFCAD_MODEL_MAX", "opus")    # escalation model (hard requests)
AUTOROUTE = os.environ.get("GRIFCAD_AUTOROUTE", "1").lower() not in ("0", "false", "no", "off")
MODEL_ID = "grif-cad"

# Slicers offered as a per-person preference. Both buttons always show; the
# SLICER_DEFAULT one is listed first. Headless /slice stays OrcaSlicer (the only
# reliably scriptable slicer on macOS) — this preference governs the GUI launch.
SLICERS = {
    "orca":     {"label": "OrcaSlicer",     "app": "OrcaSlicer"},
    "creality": {"label": "Creality Print", "app": "Creality Print"},
}
SLICER_DEFAULT = os.environ.get("SLICER_DEFAULT", "orca").lower()
if SLICER_DEFAULT not in SLICERS:
    SLICER_DEFAULT = "orca"

VENV_PY = PROJECT_DIR / ".venv" / "bin" / "python"
OPENSCAD_APP = "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD"

PERSONA = (
    "You are GrifCAD, a friendly workshop helper that designs 3D-printable parts with "
    "a kid and their parent. Use simple, encouraging language and explain what you are "
    "building. When fit matters, ask for real caliper measurements instead of guessing. "
    "Whenever you create or change a model, render it with `scripts/render.sh <file>` so "
    "a picture shows up, then describe what you made in a sentence or two. To show an "
    "existing render, read its PNG in out/preview/ (or re-run render.sh) — that makes the "
    "picture appear for the user. Never start a "
    "physical print — sending a job to the printer is always a grown-up's explicit decision."
)


def allowed_tools() -> str:
    # Claude Code wildcard syntax is Bash(prefix:*). cwd is the project root, so
    # cover the relative forms Claude actually uses, plus absolute as a backstop.
    p = str(PROJECT_DIR)
    rules = [
        "Read", "Edit", "Write", "Glob", "Grep",
        # render (the visual loop)
        "Bash(bash scripts/render.sh:*)",
        "Bash(./scripts/render.sh:*)",
        "Bash(scripts/render.sh:*)",
        f"Bash(bash {p}/scripts/render.sh:*)",
        # slice — safe (produces G-code, no physical action)
        "Bash(bash scripts/slice.sh:*)",
        "Bash(scripts/slice.sh:*)",
        # cad tooling
        "Bash(openscad:*)",
        f"Bash({OPENSCAD_APP}:*)",
        f"Bash({VENV_PY}:*)",
        # harmless fs helpers
        "Bash(mkdir:*)", "Bash(ls:*)", "Bash(cat:*)",
    ]
    # Intentionally NOT allowed: print.sh / curl to the printer — the physical-print
    # gate stays human-only. Never add --dangerously-skip-permissions here.
    return ",".join(rules)


# conversation fingerprint -> claude session_id (in-memory; reset on restart)
SESSIONS: dict[str, str] = {}

app = FastAPI(title="grif-cad bridge")
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/files", StaticFiles(directory=str(PREVIEW_DIR)), name="files")


# ---------------------------------------------------------------- helpers
def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return str(content or "")


def conversation_key(messages: list) -> str:
    for m in messages:
        if m.get("role") == "user":
            return hashlib.sha1(text_of(m.get("content")).encode()).hexdigest()
    return "default"


def snapshot_previews() -> dict[str, float]:
    return {p.name: p.stat().st_mtime for p in PREVIEW_DIR.glob("*.png")}


def changed_previews(before: dict[str, float]) -> list[str]:
    out = []
    for p in sorted(PREVIEW_DIR.glob("*.png")):
        if before.get(p.name) != p.stat().st_mtime:
            out.append(p.name)
    return out


def image_markdown(names: list[str]) -> str:
    if not names:
        return ""
    rows = [""]
    for n in names:
        v = int(PREVIEW_DIR.joinpath(n).stat().st_mtime)
        rows.append(f"![{n}]({PUBLIC_BASE}/files/{n}?v={v})")
    return "\n".join(rows) + "\n"


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", name or "")


def model_bases(png_names) -> list[str]:
    # "wall_mount-iso.png" -> "wall_mount"
    bases = set()
    for nm in png_names:
        m = re.match(r"(.+?)-(iso|front|side|top)\.png$", nm)
        if m:
            bases.add(m.group(1))
    return sorted(bases)


def find_openscad() -> Optional[str]:
    from shutil import which
    import glob
    o = which("openscad")
    if o:
        return o
    for p in glob.glob("/Applications/OpenSCAD*.app/Contents/MacOS/OpenSCAD"):
        if os.access(p, os.X_OK):
            return p
    return None


def ensure_stl(name: str) -> Optional[Path]:
    """Path to PREVIEW_DIR/<name>.stl, exporting from the OpenSCAD source if needed."""
    n = safe_name(name)
    if not n:
        return None
    stl = PREVIEW_DIR / f"{n}.stl"
    if stl.exists():
        return stl
    src = SCAD_DIR / f"{n}.scad"
    osc = find_openscad()
    if src.exists() and osc:
        try:
            subprocess.run([osc, "-o", str(stl), str(src)],
                           check=True, capture_output=True, timeout=120)
        except Exception:
            return None
        return stl if stl.exists() else None
    return None


def slicer_order() -> list[str]:
    return [SLICER_DEFAULT] + [k for k in SLICERS if k != SLICER_DEFAULT]


def app_installed(appname: str) -> bool:
    return any((Path(base) / f"{appname}.app").exists()
               for base in ("/Applications", str(Path.home() / "Applications")))


def action_links(png_names) -> str:
    rows = []
    for b in model_bases(png_names):
        parts = [f"**[🔄 Spin it around]({PUBLIC_BASE}/view/{b})**"]
        for key in slicer_order():
            label = SLICERS[key]["label"]
            parts.append(f"**[🛠 Open in {label}]({PUBLIC_BASE}/slicer/open?model={b}&app={key})**")
        rows.append("  ·  ".join(parts))
    return ("\n" + "  \n".join(rows) + "\n") if rows else ""


# Self-contained three.js STL viewer (drag to orbit, scroll to zoom). __NAME__ is substituted.
VIEWER_HTML = r"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__NAME__ · grif-cad</title>
<style>
  html,body{margin:0;height:100%;background:#1e1e2e;overflow:hidden;font-family:system-ui}
  #c{display:block;width:100vw;height:100vh}
  .tag{position:fixed;top:10px;left:14px;color:#bac2de;font-size:14px;pointer-events:none}
  .err{position:fixed;inset:0;display:grid;place-items:center;color:#f38ba8;padding:2rem;text-align:center}
</style>
<script type="importmap">
{"imports":{
  "three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
  "three/addons/":"https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"
}}
</script></head>
<body>
<div class="tag">__NAME__ — drag to spin · scroll to zoom</div>
<canvas id="c"></canvas>
<script type="module">
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {STLLoader} from 'three/addons/loaders/STLLoader.js';
const canvas=document.getElementById('c');
const renderer=new THREE.WebGLRenderer({canvas,antialias:true});
renderer.setPixelRatio(devicePixelRatio); renderer.setSize(innerWidth,innerHeight);
const scene=new THREE.Scene(); scene.background=new THREE.Color(0x1e1e2e);
const camera=new THREE.PerspectiveCamera(45,innerWidth/innerHeight,0.1,10000);
const controls=new OrbitControls(camera,canvas); controls.enableDamping=true;
scene.add(new THREE.HemisphereLight(0xffffff,0x445566,1.1));
const dir=new THREE.DirectionalLight(0xffffff,1.3); dir.position.set(1,1.4,2); scene.add(dir);
new STLLoader().load('/files/__NAME__.stl', geo=>{
  geo.computeVertexNormals(); geo.center();
  const mat=new THREE.MeshStandardMaterial({color:0x4f8cff,metalness:0.1,roughness:0.55});
  const mesh=new THREE.Mesh(geo,mat); mesh.rotation.x=-Math.PI/2; scene.add(mesh);
  geo.computeBoundingSphere(); const r=(geo.boundingSphere&&geo.boundingSphere.radius)||50;
  camera.position.set(r*1.9,r*1.5,r*1.9); controls.target.set(0,0,0); controls.update();
}, undefined, ()=>{ document.body.innerHTML='<div class="err">Could not load the 3D model.</div>'; });
addEventListener('resize',()=>{camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();renderer.setSize(innerWidth,innerHeight);});
(function loop(){requestAnimationFrame(loop);controls.update();renderer.render(scene,camera);})();
</script></body></html>
"""


# Requests matching these signals escalate from the base model to MODEL_MAX (opus).
HARD_SIGNALS = re.compile(
    r"\b(assembl(?:y|e|ies|ed)|mating|mate|snap[- ]?fit|press[- ]?fit|interlock|"
    r"mechanism|gear|gears|thread(?:ed|s)?|bearing|hinge|linkage|joint|"
    r"toleranc(?:e|es)|clearance|precise|precision|exact fit|"
    r"lattice|honeycomb|gyroid|loft(?:ed)?|sweep|spline|organic|ergonomic|"
    r"cadquery|step file|\.step|multi[- ]?part|multiple parts|"
    r"complex|complicated|intricate|advanced)\b",
    re.IGNORECASE,
)


def choose_model(prompt: str) -> str:
    low = (prompt or "").lower()
    if re.search(r"\b(?:use|in|with) opus\b", low):        # explicit override wins
        return MODEL_MAX
    if re.search(r"\b(?:use|in|with) sonnet\b", low):
        return MODEL
    if AUTOROUTE and HARD_SIGNALS.search(prompt or ""):
        return MODEL_MAX
    return MODEL


def build_cmd(prompt: str, session_id: Optional[str], model: str) -> list[str]:
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--model", model,
        "--append-system-prompt", PERSONA,
        "--permission-mode", "acceptEdits",
        "--allowedTools", allowed_tools(),
    ]
    if session_id:
        cmd += ["--resume", session_id]
    return cmd


async def run_claude(prompt: str, key: str):
    """Async-yield (kind, text): kind in {text, status, done}."""
    before = snapshot_previews()
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)  # force the subscription path

    model = choose_model(prompt)
    print(f"[grif-cad] model={model}", flush=True)
    proc = await asyncio.create_subprocess_exec(
        *build_cmd(prompt, SESSIONS.get(key), model),
        cwd=str(PROJECT_DIR), env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        limit=16 * 1024 * 1024,   # stream-json is one JSON object per line; a line carrying a
                                  # read image easily exceeds asyncio's 64 KiB readline default
    )

    final_session = SESSIONS.get(key)
    produced = False
    read_pngs: set[str] = set()
    assert proc.stdout is not None
    async for raw in proc.stdout:
        line = raw.decode(errors="replace").strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = ev.get("type")
        if kind == "system" and ev.get("session_id"):
            final_session = ev["session_id"]
        elif kind == "assistant":
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") == "text" and block.get("text"):
                    produced = True
                    yield ("text", block["text"])
                elif block.get("type") == "tool_use":
                    name = block.get("name", "tool")
                    yield ("status", f"\n_🛠 {name}…_\n")
                    if name == "Read":
                        fp = (block.get("input") or {}).get("file_path", "")
                        if fp.endswith(".png") and (PREVIEW_DIR / Path(fp).name).exists():
                            read_pngs.add(Path(fp).name)   # surface previews the agent looked at
        elif kind == "result" and ev.get("session_id"):
            final_session = ev["session_id"]

    err = b""
    if proc.stderr is not None:
        err = await proc.stderr.read()
    await proc.wait()

    if final_session:
        SESSIONS[key] = final_session
    if proc.returncode and not produced:
        msg = err.decode(errors="replace").strip()[:500] or f"exit {proc.returncode}"
        yield ("text", f"\n⚠️ build error: {msg}\n")

    surfaced = sorted(set(changed_previews(before)) | read_pngs)
    imgs = image_markdown(surfaced) + action_links(surfaced)
    if imgs:
        yield ("text", imgs)
    yield ("done", "")


# ---------------------------------------------------------------- OpenAI shapes
def chunk(delta: dict, finish=None) -> str:
    payload = {
        "id": "chatcmpl-grifcad",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": MODEL_ID,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    return f"data: {json.dumps(payload)}\n\n"


@app.get("/v1/models")
async def models():
    return {
        "object": "list",
        "data": [{"id": MODEL_ID, "object": "model", "created": int(time.time()), "owned_by": "grif-cad"}],
    }


@app.post("/v1/chat/completions")
async def chat_completions(req: Request):
    body = await req.json()
    messages = body.get("messages", [])
    prompt = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            prompt = text_of(m.get("content"))
            break
    key = conversation_key(messages)

    if body.get("stream"):
        async def gen():
            yield chunk({"role": "assistant"})
            try:
                async for kind, text in run_claude(prompt, key):
                    if kind in ("text", "status") and text:
                        yield chunk({"content": text})
                    elif kind == "done":
                        yield chunk({}, finish="stop")
            except Exception as e:  # never truncate the HTTP stream — close it cleanly
                yield chunk({"content": f"\n⚠️ bridge error: {e}\n"})
                yield chunk({}, finish="stop")
            yield "data: [DONE]\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")

    parts = []
    async for kind, text in run_claude(prompt, key):
        if kind in ("text", "status"):
            parts.append(text)
    return JSONResponse({
        "id": "chatcmpl-grifcad",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": MODEL_ID,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "".join(parts)}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    })


@app.get("/healthz")
async def healthz():
    return {"ok": True, "project": str(PROJECT_DIR),
            "model": MODEL, "escalate_to": MODEL_MAX, "autoroute": AUTOROUTE}


@app.get("/view/{name}")
async def view(name: str):
    """Interactive three.js viewer — drag to spin the model around."""
    if ensure_stl(name) is None:
        return HTMLResponse(
            "<p style='font-family:system-ui'>No 3D model yet — ask the assistant to build and render it first.</p>",
            status_code=404,
        )
    return HTMLResponse(VIEWER_HTML.replace("__NAME__", safe_name(name)))


@app.get("/slicer/open")
async def slicer_open(model: str = "", app: str = ""):
    """Launch the chosen slicer's GUI on the host with the model, for further edits."""
    n = safe_name(model)
    key = (app or SLICER_DEFAULT).lower()
    if key not in SLICERS:
        key = SLICER_DEFAULT
    appname = SLICERS[key]["app"]
    if not app_installed(appname):
        return HTMLResponse(
            f"<p style='font-family:system-ui'>{appname} isn't installed. Install it, or use the other slicer button.</p>",
            status_code=404)
    target = next((PREVIEW_DIR / f"{n}{ext}" for ext in (".3mf", ".stl")
                   if (PREVIEW_DIR / f"{n}{ext}").exists()), None)
    if target is None:
        target = ensure_stl(n)
    if target is None:
        return HTMLResponse(
            f"<p style='font-family:system-ui'>No model file for '{n}'. Render it first.</p>", status_code=404)
    try:
        subprocess.Popen(["open", "-a", appname, str(target)])
    except Exception as e:
        return HTMLResponse(
            f"<p style='font-family:system-ui'>Couldn't launch {appname}: {e}</p>", status_code=500)
    return HTMLResponse(
        f"<p style='font-family:system-ui'>Launching {appname} with <b>{target.name}</b>… you can close this tab.</p>")
