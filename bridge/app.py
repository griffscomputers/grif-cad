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
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# ---------------------------------------------------------------- config
PROJECT_DIR = Path(os.environ.get("PROJECT_DIR", Path(__file__).resolve().parent.parent))
PREVIEW_DIR = PROJECT_DIR / "out" / "preview"
PORT = int(os.environ.get("PORT", "8765"))
PUBLIC_BASE = os.environ.get("PUBLIC_BASE", f"http://localhost:{PORT}").rstrip("/")
MODEL = os.environ.get("GRIFCAD_MODEL", "sonnet")
MODEL_ID = "grif-cad"

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


def build_cmd(prompt: str, session_id: Optional[str]) -> list[str]:
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--model", MODEL,
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

    proc = await asyncio.create_subprocess_exec(
        *build_cmd(prompt, SESSIONS.get(key)),
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
    imgs = image_markdown(surfaced)
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
    return {"ok": True, "project": str(PROJECT_DIR), "model": MODEL}
