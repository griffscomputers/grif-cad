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
import base64
import hashlib
import hmac
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
# Each part lives in its own folder projects/<slug>/ holding all of its files. The bridge
# serves that tree at /files/<slug>/<file> and surfaces renders from projects/*/*.png.
PROJECTS_DIR = PROJECT_DIR / "projects"
PORT = int(os.environ.get("PORT", "8765"))
PUBLIC_BASE = os.environ.get("PUBLIC_BASE", f"http://localhost:{PORT}").rstrip("/")
# Shared secret guarding /v1/*. Open WebUI already sends its OpenAI "API key" as an
# Authorization: Bearer header, so honouring it costs no UI-side plumbing. Empty means
# the bridge is OPEN — run.sh warns loudly, and SECURITY.md explains why that is a
# LAN-exposed AI agent with write access. setup.sh generates one on first run.
BRIDGE_TOKEN = os.environ.get("BRIDGE_TOKEN", "").strip()
MODEL = os.environ.get("GRIFCAD_MODEL", "sonnet")          # base model (normal requests)
MODEL_MAX = os.environ.get("GRIFCAD_MODEL_MAX", "opus")    # escalation model (hard requests)
AUTOROUTE = os.environ.get("GRIFCAD_AUTOROUTE", "1").lower() not in ("0", "false", "no", "off")
MODEL_ID = "grif-cad"

# Meshy-style modes, each advertised as its own model id so Open WebUI's picker
# doubles as the mode switcher. Live modes share the pipeline and differ only by a
# persona suffix; parked modes answer instantly without spawning claude.
PARKED_MSG = (
    "**{label} is coming soon!** 🚧\n\nThis mode needs image generation, which our "
    "workshop brain can't do yet. Meanwhile, try **3D Agent** or **Text to 3D** — "
    "they build real printable parts."
)

MODES: dict[str, dict] = {
    MODEL_ID: {  # 3D Agent — the default conversational pipeline
        "label": "3D Agent", "parked": False, "wants_image": False,
        "persona_suffix": ""},
    "grif-cad-text-to-3d": {
        "label": "Text to 3D", "parked": False, "wants_image": False,
        "persona_suffix": (
            " ONE-SHOT MODE: do not ask clarifying questions. Pick sensible printable "
            "dimensions, state your assumptions in one line, create the project folder, "
            "model the part, render it, and deliver — all in this single turn.")},
    "grif-cad-image-to-3d": {
        "label": "Image to 3D", "parked": False, "wants_image": True,
        "persona_suffix": (
            " IMAGE RECONSTRUCTION MODE: the message lists file path(s) of reference "
            "image(s) the user attached. Read each image FIRST. Rebuild what you see as "
            "parametric CAD (not a mesh copy): identify the primitive shapes, estimate "
            "dimensions from visual context and say what you assumed, then model and "
            "render it, and offer to refine with real measurements. Copy the reference "
            "image into the part's folder with cp for provenance.")},
    "grif-cad-texturing": {
        "label": "AI Texturing", "parked": True},
    "grif-cad-image-gen": {
        "label": "AI Image Generator", "parked": True},
}

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
    "building. Each part gets its OWN folder projects/<slug>/ (pick a short kebab-case "
    "<slug>): start it with `scripts/project.sh new <slug>`, or write projects/<slug>/<slug>.scad "
    "directly. Whenever you create or change a model, render it with "
    "`scripts/render.sh projects/<slug>/<slug>.scad` (or `scripts/project.sh render <slug>`) so a "
    "picture shows up in its folder, then describe what you made in a sentence or two. To show an "
    "existing render, read its PNG in projects/<slug>/ — that makes the picture appear for the user. "
    "When fit matters, ask for real caliper measurements instead of guessing. Never start a "
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
        # per-part project folders + catalog
        "Bash(bash scripts/project.sh:*)",
        "Bash(./scripts/project.sh:*)",
        "Bash(scripts/project.sh:*)",
        f"Bash(bash {p}/scripts/project.sh:*)",
        # slice — safe (produces G-code, no physical action)
        "Bash(bash scripts/slice.sh:*)",
        "Bash(scripts/slice.sh:*)",
        # find existing models (Thingiverse search/download + browser links)
        "Bash(python3 scripts/find_model.py:*)",
        "Bash(scripts/find_model.py:*)",
        # cad tooling
        "Bash(openscad:*)",
        f"Bash({OPENSCAD_APP}:*)",
        f"Bash({VENV_PY}:*)",
        # harmless fs helpers (cp: copy reference images into part folders for provenance)
        "Bash(mkdir:*)", "Bash(ls:*)", "Bash(cat:*)", "Bash(cp:*)",
    ]
    # Intentionally NOT allowed: print.sh / curl to the printer — the physical-print
    # gate stays human-only. Never add --dangerously-skip-permissions here.
    return ",".join(rules)


# conversation fingerprint -> claude session_id (in-memory; reset on restart)
SESSIONS: dict[str, str] = {}

app = FastAPI(title="grif-cad bridge")
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/files", StaticFiles(directory=str(PROJECTS_DIR)), name="files")


@app.middleware("http")
async def require_token(request: Request, call_next):
    """Bearer gate on /v1/*.

    Scoped to /v1 deliberately: those are the OpenAI-client routes, and an OpenAI
    client always sends the header. The browser-facing pages (/files, /view, /studio,
    /slicer/open) are loaded directly by the browser as top-level URLs or <img> src,
    which cannot carry an Authorization header. /healthz stays open so `stack.sh
    check` works without holding the secret.
    """
    if BRIDGE_TOKEN and request.url.path.startswith("/v1/"):
        sent = request.headers.get("authorization", "")
        scheme, _, value = sent.partition(" ")
        # compare_digest on both halves: constant-time, and never leaks length via
        # an early return on the scheme check.
        if scheme.lower() != "bearer" or not hmac.compare_digest(value.strip(), BRIDGE_TOKEN):
            return JSONResponse(
                {"error": {"message": "Invalid or missing bearer token. See SECURITY.md.",
                           "type": "invalid_request_error", "code": "invalid_api_key"}},
                status_code=401,
            )
    return await call_next(request)


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


def conversation_key(messages: list, model_id: str = "") -> str:
    # Keyed on mode + first user message. Image parts count too, otherwise every
    # photo-first chat would hash sha1("") and share one claude session.
    for m in messages:
        if m.get("role") == "user":
            h = hashlib.sha1(model_id.encode())
            h.update(text_of(m.get("content")).encode())
            c = m.get("content")
            if isinstance(c, list):
                for part in c:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        h.update((part.get("image_url") or {}).get("url", "")[:4096].encode())
            return h.hexdigest()
    return "default"


UPLOADS_DIR = PROJECT_DIR / "uploads"   # gitignored. Deliberately NOT under projects/:
                                        # snapshot_previews() globs projects/*/*.png and would
                                        # echo an uploaded photo back into chat as a "render".
DATA_URL_RE = re.compile(r"^data:image/(png|jpe?g|webp|gif);base64,(.+)$", re.S)


def save_images(content) -> list[Path]:
    """Persist image_url data-URL parts to uploads/ (content-hash names dedupe re-sends)."""
    out: list[Path] = []
    if not isinstance(content, list):
        return out
    for part in content:
        if not (isinstance(part, dict) and part.get("type") == "image_url"):
            continue
        m = DATA_URL_RE.match((part.get("image_url") or {}).get("url", ""))
        if not m:
            continue
        try:
            data = base64.b64decode(m.group(2))
        except Exception:
            continue
        # 10 MB cap: claude echoes a Read image as one base64 stream-json line;
        # keep that comfortably under the subprocess readline limit.
        if not data or len(data) > 10 * 1024 * 1024:
            continue
        ext = {"jpeg": "jpg"}.get(m.group(1), m.group(1))
        UPLOADS_DIR.mkdir(exist_ok=True)
        p = UPLOADS_DIR / f"{hashlib.sha1(data).hexdigest()[:12]}.{ext}"
        if not p.exists():
            p.write_bytes(data)
        out.append(p)
    return out[:4]


def _rel(p: Path) -> str:
    return str(p.relative_to(PROJECTS_DIR))      # "<slug>/<file>.png"


def snapshot_previews() -> dict[str, float]:
    return {_rel(p): p.stat().st_mtime for p in PROJECTS_DIR.glob("*/*.png")}


def changed_previews(before: dict[str, float]) -> list[str]:
    out = []
    for p in sorted(PROJECTS_DIR.glob("*/*.png")):
        rel = _rel(p)
        if before.get(rel) != p.stat().st_mtime:
            out.append(rel)
    return out


def image_markdown(names: list[str]) -> str:
    if not names:
        return ""
    rows = [""]
    for n in names:                              # n is "<slug>/<file>.png"
        v = int(PROJECTS_DIR.joinpath(n).stat().st_mtime)
        rows.append(f"![{Path(n).name}]({PUBLIC_BASE}/files/{n}?v={v})")
    return "\n".join(rows) + "\n"


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", name or "")


def model_bases(png_names) -> list[str]:
    # "wall_mount/wall_mount-iso.png" -> slug "wall_mount" (the folder is the identity)
    slugs = set()
    for nm in png_names:
        m = re.match(r"([^/]+)/.+-(iso|front|side|top)\.png$", nm)
        if m:
            slugs.add(m.group(1))
    return sorted(slugs)


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
    """Path to projects/<slug>/<slug>.stl, exporting from the source if it isn't there yet."""
    n = safe_name(name)
    if not n:
        return None
    folder = PROJECTS_DIR / n
    stl = folder / f"{n}.stl"
    if stl.exists():
        return stl
    src_scad = folder / f"{n}.scad"
    osc = find_openscad()
    if src_scad.exists() and osc:
        try:
            subprocess.run([osc, "-o", str(stl), str(src_scad)],
                           check=True, capture_output=True, timeout=120)
        except Exception:
            return None
        return stl if stl.exists() else None
    src_py = folder / f"{n}.py"          # CadQuery: running it exports the stl beside itself
    if src_py.exists() and VENV_PY.exists():
        try:
            subprocess.run([str(VENV_PY), str(src_py)], cwd=str(PROJECT_DIR),
                           check=True, capture_output=True, timeout=180)
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
    if rows:
        rows.append(f"**[📚 All parts]({PUBLIC_BASE}/studio)**")
    return ("\n" + "  \n".join(rows) + "\n") if rows else ""


# Studio look shared by /studio and /view — Meshy-style near-black with a blue accent.
STUDIO_BG = "#0a0c12"
STUDIO_PANEL = "#12141d"
STUDIO_BORDER = "#1d2230"
STUDIO_ACCENT = "#4f8cff"

# Self-contained three.js STL viewer (drag to orbit, scroll to zoom).
# __NAME__ and __SLICERS__ (header buttons html) are substituted.
VIEWER_HTML = r"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__NAME__ · GrifCAD Studio</title>
<style>
  html,body{margin:0;height:100%;background:#0a0c12;overflow:hidden;font-family:system-ui}
  #c{display:block;width:100vw;height:100vh}
  header{position:fixed;top:0;left:0;right:0;display:flex;align-items:center;gap:14px;
    padding:10px 16px;background:#12141dd9;backdrop-filter:blur(8px);
    border-bottom:1px solid #1d2230;font-size:14px;z-index:2}
  header a{color:#8b93a7;text-decoration:none;padding:4px 10px;border-radius:8px}
  header a:hover{color:#e6e9f2;background:#1d2230}
  header .name{color:#e6e9f2;font-weight:600;margin-right:auto}
  header a.btn{border:1px solid #1d2230;color:#c8cede}
  header a.btn:hover{border-color:#4f8cff;color:#fff}
  .hint{position:fixed;bottom:12px;left:16px;color:#5c6478;font-size:12px;pointer-events:none}
  .err{position:fixed;inset:0;display:grid;place-items:center;color:#f38ba8;padding:2rem;text-align:center}
</style>
<script type="importmap">
{"imports":{
  "three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
  "three/addons/":"https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"
}}
</script></head>
<body>
<header><a href="/studio">&larr; All parts</a><span class="name">__NAME__</span>__SLICERS__</header>
<div class="hint">drag to spin · scroll to zoom</div>
<canvas id="c"></canvas>
<script type="module">
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {STLLoader} from 'three/addons/loaders/STLLoader.js';
const canvas=document.getElementById('c');
const renderer=new THREE.WebGLRenderer({canvas,antialias:true});
renderer.setPixelRatio(devicePixelRatio); renderer.setSize(innerWidth,innerHeight);
const scene=new THREE.Scene(); scene.background=new THREE.Color(0x0a0c12);
const camera=new THREE.PerspectiveCamera(45,innerWidth/innerHeight,0.1,10000);
const controls=new OrbitControls(camera,canvas); controls.enableDamping=true;
scene.add(new THREE.HemisphereLight(0xffffff,0x445566,1.1));
const dir=new THREE.DirectionalLight(0xffffff,1.3); dir.position.set(1,1.4,2); scene.add(dir);
new STLLoader().load('/files/__NAME__/__NAME__.stl', geo=>{
  geo.computeVertexNormals(); geo.center();
  const mat=new THREE.MeshStandardMaterial({color:0x4f8cff,metalness:0.1,roughness:0.55});
  const mesh=new THREE.Mesh(geo,mat); mesh.rotation.x=-Math.PI/2; scene.add(mesh);
  geo.computeBoundingSphere(); const r=(geo.boundingSphere&&geo.boundingSphere.radius)||50;
  const grid=new THREE.GridHelper(r*4, 20, 0x2a3040, 0x161a26);
  grid.position.y=-r*1.05; scene.add(grid);
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


def build_cmd(prompt: str, session_id: Optional[str], model: str,
              persona: str = PERSONA) -> list[str]:
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--model", model,
        "--append-system-prompt", persona,
        "--permission-mode", "acceptEdits",
        "--allowedTools", allowed_tools(),
    ]
    if session_id:
        cmd += ["--resume", session_id]
    return cmd


async def run_claude(prompt: str, key: str, persona_suffix: str = ""):
    """Async-yield (kind, text): kind in {text, status, done}."""
    before = snapshot_previews()
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)  # force the subscription path

    model = choose_model(prompt)
    print(f"[grif-cad] model={model}", flush=True)
    proc = await asyncio.create_subprocess_exec(
        *build_cmd(prompt, SESSIONS.get(key), model, PERSONA + persona_suffix),
        cwd=str(PROJECT_DIR), env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        limit=32 * 1024 * 1024,   # stream-json is one JSON object per line; a Read of a 10 MB
                                  # uploaded image echoes ~13.7 MB of base64 on a single line
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
                        if fp.endswith(".png"):
                            ap = Path(fp)
                            if not ap.is_absolute():
                                ap = PROJECT_DIR / ap
                            try:                       # surface previews the agent looked at
                                rel = ap.resolve().relative_to(PROJECTS_DIR.resolve())
                                if (PROJECTS_DIR / rel).exists():
                                    read_pngs.add(str(rel))
                            except Exception:
                                pass
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
def chunk(delta: dict, finish=None, model: str = MODEL_ID) -> str:
    payload = {
        "id": "chatcmpl-grifcad",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    return f"data: {json.dumps(payload)}\n\n"


def static_reply(text: str, model_id: str, stream: bool):
    """Instant canned answer (parked modes, missing-image nudge) — no claude spawn."""
    if stream:
        async def gen():
            yield chunk({"role": "assistant"}, model=model_id)
            yield chunk({"content": text}, model=model_id)
            yield chunk({}, finish="stop", model=model_id)
            yield "data: [DONE]\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")
    return JSONResponse({
        "id": "chatcmpl-grifcad",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_id,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    })


@app.get("/v1/models")
async def models():
    now = int(time.time())
    return {
        "object": "list",
        "data": [{"id": mid, "object": "model", "created": now, "owned_by": "grif-cad"}
                 for mid in MODES],
    }


@app.post("/v1/chat/completions")
async def chat_completions(req: Request):
    body = await req.json()
    model_id = body.get("model") if body.get("model") in MODES else MODEL_ID
    mode = MODES[model_id]
    stream = bool(body.get("stream"))

    if mode["parked"]:
        return static_reply(PARKED_MSG.format(label=mode["label"]), model_id, stream)

    messages = body.get("messages", [])
    prompt, images = "", []
    for m in reversed(messages):
        if m.get("role") == "user":
            prompt = text_of(m.get("content"))
            # Only the LAST user message: Open WebUI resends full history each turn;
            # earlier attachments were handled on their own turn (hash names dedupe anyway).
            images = save_images(m.get("content"))
            break
    if images:
        prompt += ("\n\n[Attached reference image(s) — Read these files before designing:]\n"
                   + "\n".join(f"- {p}" for p in images))
    elif mode.get("wants_image"):
        return static_reply(
            "📷 **Attach a photo or sketch first** (the + button next to the message box), "
            "then tell me what it is and I'll rebuild it as a printable part!",
            model_id, stream)
    key = conversation_key(messages, model_id)
    suffix = mode.get("persona_suffix", "")

    if stream:
        async def gen():
            yield chunk({"role": "assistant"}, model=model_id)
            try:
                async for kind, text in run_claude(prompt, key, suffix):
                    if kind in ("text", "status") and text:
                        yield chunk({"content": text}, model=model_id)
                    elif kind == "done":
                        yield chunk({}, finish="stop", model=model_id)
            except Exception as e:  # never truncate the HTTP stream — close it cleanly
                yield chunk({"content": f"\n⚠️ bridge error: {e}\n"}, model=model_id)
                yield chunk({}, finish="stop", model=model_id)
            yield "data: [DONE]\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")

    parts = []
    async for kind, text in run_claude(prompt, key, suffix):
        if kind in ("text", "status"):
            parts.append(text)
    return JSONResponse({
        "id": "chatcmpl-grifcad",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_id,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "".join(parts)}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    })


@app.get("/healthz")
async def healthz():
    return {"ok": True, "project": str(PROJECT_DIR),
            "model": MODEL, "escalate_to": MODEL_MAX, "autoroute": AUTOROUTE}


def slicer_buttons_html(slug: str) -> str:
    return "".join(
        f'<a class="btn" href="/slicer/open?model={slug}&amp;app={key}">🛠 {SLICERS[key]["label"]}</a>'
        for key in slicer_order()
    )


@app.get("/view/{name}")
async def view(name: str):
    """Interactive three.js viewer — drag to spin the model around."""
    n = safe_name(name)
    if ensure_stl(n) is None:
        return HTMLResponse(
            "<p style='font-family:system-ui'>No 3D model yet — ask the assistant to build and render it first.</p>",
            status_code=404,
        )
    return HTMLResponse(VIEWER_HTML.replace("__NAME__", n)
                                   .replace("__SLICERS__", slicer_buttons_html(n)))


def catalog() -> dict[str, dict]:
    """projects/index.tsv rows keyed by slug (missing/short rows tolerated)."""
    out: dict[str, dict] = {}
    tsv = PROJECTS_DIR / "index.tsv"
    if not tsv.exists():
        return out
    lines = tsv.read_text().splitlines()
    for line in lines[1:]:                      # skip header: slug created updated engine title …
        cols = line.split("\t")
        if cols and cols[0]:
            out[cols[0]] = {
                "updated": (cols[2] if len(cols) > 2 else "")[:10],
                "engine": cols[3] if len(cols) > 3 else "",
                "title": cols[4] if len(cols) > 4 else "",
            }
    return out


@app.get("/studio")
async def studio():
    """Meshy-style asset library — every part in projects/, newest first."""
    meta = catalog()
    cards = []
    parts = [d for d in PROJECTS_DIR.iterdir()
             if d.is_dir() and re.fullmatch(r"[a-z0-9][a-z0-9_-]*", d.name)]
    parts.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    for d in parts:
        slug = d.name
        m = meta.get(slug, {})
        title = m.get("title") or slug.replace("_", " ").replace("-", " ").title()
        engine = m.get("engine", "")
        updated = m.get("updated", "")
        thumb = d / f"{slug}-iso.png"
        if thumb.exists():
            img = (f'<img src="/files/{slug}/{thumb.name}?v={int(thumb.stat().st_mtime)}" '
                   f'alt="{title}" loading="lazy">')
        else:
            img = '<div class="noimg">no render yet</div>'
        badge = f'<span class="badge">{engine}</span>' if engine else ""
        when = f'<span class="when">{updated}</span>' if updated else ""
        cards.append(f"""
    <div class="card">
      <a class="thumb" href="/view/{slug}">{img}</a>
      <div class="meta">
        <a class="title" href="/view/{slug}">{title}</a>
        <div class="sub">{slug} {badge} {when}</div>
        <div class="actions">{slicer_buttons_html(slug)}</div>
      </div>
    </div>""")
    body = "\n".join(cards) if cards else '<p class="empty">No parts yet — go make something!</p>'
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GrifCAD Studio</title>
<style>
  :root{{color-scheme:dark}}
  html,body{{margin:0;background:{STUDIO_BG};color:#e6e9f2;font-family:system-ui}}
  header{{display:flex;align-items:baseline;gap:14px;padding:22px 28px 8px}}
  h1{{margin:0;font-size:22px;font-weight:700}}
  h1 .accent{{color:{STUDIO_ACCENT}}}
  .count{{color:#5c6478;font-size:13px}}
  header .new{{margin-left:auto;font-size:14px;color:#c8cede;text-decoration:none;
    border:1px solid {STUDIO_BORDER};border-radius:10px;padding:8px 14px}}
  header .new:hover{{border-color:{STUDIO_ACCENT};color:#fff}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));
    gap:18px;padding:18px 28px 40px}}
  .card{{background:{STUDIO_PANEL};border:1px solid {STUDIO_BORDER};border-radius:14px;
    overflow:hidden;transition:border-color .15s}}
  .card:hover{{border-color:{STUDIO_ACCENT}}}
  .thumb{{display:block;aspect-ratio:4/3;background:#0e1017}}
  .thumb img{{width:100%;height:100%;object-fit:cover;display:block}}
  .noimg{{display:grid;place-items:center;height:100%;color:#3a4154;font-size:13px}}
  .meta{{padding:12px 14px 14px}}
  .title{{color:#e6e9f2;text-decoration:none;font-weight:600;font-size:15px}}
  .title:hover{{color:{STUDIO_ACCENT}}}
  .sub{{color:#5c6478;font-size:12px;margin:4px 0 10px}}
  .badge{{background:#1a2233;color:{STUDIO_ACCENT};border-radius:6px;padding:1px 7px;font-size:11px}}
  .when{{margin-left:6px}}
  .actions{{display:flex;gap:8px;flex-wrap:wrap}}
  .actions a{{font-size:12px;color:#c8cede;text-decoration:none;border:1px solid {STUDIO_BORDER};
    border-radius:8px;padding:4px 9px}}
  .actions a:hover{{border-color:{STUDIO_ACCENT};color:#fff}}
  .empty{{padding:40px 28px;color:#5c6478}}
</style></head>
<body>
<header><h1>Grif<span class="accent">CAD</span> Studio</h1>
  <span class="count">{len(parts)} part{"s" if len(parts) != 1 else ""}</span>
  <a class="new" href="http://localhost:3000">✨ New part — open the chat</a></header>
<div class="grid">{body}</div>
</body></html>"""
    return HTMLResponse(html)


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
    folder = PROJECTS_DIR / n
    target = next((folder / f"{n}{ext}" for ext in (".3mf", ".stl")
                   if (folder / f"{n}{ext}").exists()), None)
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
