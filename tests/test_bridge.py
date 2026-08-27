"""Bridge unit tests — no stack, no Docker, no Claude subscription required.

These are the assertions CI can actually run. The heavyweight end-to-end gate is
`scripts/stack.sh check --deep`, which needs Colima, MPS and a logged-in Claude;
this file covers the logic that can be checked in isolation.

The single most important test here is the print-gate one. Everything else is
hygiene.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bridge"))

TOKEN = "test-token-not-a-real-secret"


@pytest.fixture(scope="module")
def mod():
    """Import the bridge with a known token (module reads env at import time)."""
    os.environ["BRIDGE_TOKEN"] = TOKEN
    os.environ["PROJECT_DIR"] = str(ROOT)
    import app
    return importlib.reload(app)


@pytest.fixture(scope="module")
def client(mod):
    return TestClient(mod.app)


# --------------------------------------------------------------- the safety gate
class TestPrintGate:
    """A print is a physical action with fire risk. The web path must never reach it.

    If these fail, do not 'fix the test' — the allowlist regressed.
    """

    def test_no_print_script(self, mod):
        assert "print.sh" not in mod.allowed_tools()

    def test_no_printer_network_calls(self, mod):
        tools = mod.allowed_tools().lower()
        # Moonraker is driven over HTTP; no general-purpose fetch tool may appear.
        for forbidden in ("curl", "wget", "moonraker", "webfetch", "httpie"):
            assert forbidden not in tools, f"{forbidden!r} reachable from the web bridge"

    def test_built_command_never_skips_permissions(self, mod):
        """Assert on the actual argv, not on source text.

        A source grep here false-positives on the comment warning against the flag,
        and would miss it being assembled at runtime. The command is the truth.
        """
        cmd = mod.build_cmd("make a cube", None, "sonnet")
        assert "--dangerously-skip-permissions" not in cmd
        assert "--permission-mode" in cmd
        assert cmd[cmd.index("--permission-mode") + 1] == "acceptEdits"
        assert "--allowedTools" in cmd

    def test_no_skip_permissions_in_code(self):
        """Source scan, ignoring comments (one of which warns against the flag)."""
        for path in ("bridge/app.py", "bridge/run.sh", "scripts/stack.sh"):
            for i, line in enumerate((ROOT / path).read_text().splitlines(), 1):
                code = line.split("#", 1)[0]
                assert "dangerously-skip-permissions" not in code, f"{path}:{i}"

    def test_bash_rules_are_prefix_scoped(self, mod):
        """Every Bash(...) rule must be scoped; a bare Bash entry is a shell escape."""
        rules = mod.allowed_tools().split(",")
        assert "Bash" not in [r.strip() for r in rules]
        for r in rules:
            if r.startswith("Bash("):
                assert r.endswith(")"), f"malformed rule: {r}"


# --------------------------------------------------------------- path handling
class TestSafeName:
    @pytest.mark.parametrize("evil", [
        "../../etc/passwd", "/etc/passwd", "..%2f..%2fetc",
        "a/b", "a\\b", "a\x00b", "a b", "a;rm -rf /", "$(whoami)", "",
    ])
    def test_strips_everything_dangerous(self, mod, evil):
        out = mod.safe_name(evil)
        for ch in "/\\.\x00 ;$()":
            assert ch not in out, f"{ch!r} survived safe_name({evil!r}) -> {out!r}"

    def test_preserves_legitimate_slugs(self, mod):
        assert mod.safe_name("wall_mount") == "wall_mount"
        assert mod.safe_name("tray-peg-base") == "tray-peg-base"


# --------------------------------------------------------------- auth
class TestAuth:
    def test_healthz_stays_open(self, client):
        """stack.sh check hits this without holding the secret."""
        assert client.get("/healthz").status_code == 200

    def test_v1_requires_a_token(self, client):
        assert client.get("/v1/models").status_code == 401

    def test_v1_rejects_a_wrong_token(self, client):
        r = client.get("/v1/models", headers={"Authorization": "Bearer nope"})
        assert r.status_code == 401

    def test_v1_rejects_a_non_bearer_scheme(self, client):
        r = client.get("/v1/models", headers={"Authorization": f"Basic {TOKEN}"})
        assert r.status_code == 401

    def test_v1_accepts_the_right_token(self, client):
        r = client.get("/v1/models", headers={"Authorization": f"Bearer {TOKEN}"})
        assert r.status_code == 200

    def test_chat_completions_is_guarded(self, client):
        r = client.post("/v1/chat/completions", json={})
        assert r.status_code == 401


# --------------------------------------------------------------- modes
class TestModes:
    def test_default_model_id_is_a_mode(self, mod):
        assert mod.MODEL_ID in mod.MODES

    def test_every_mode_is_well_formed(self, mod):
        for mid, m in mod.MODES.items():
            assert "label" in m and "parked" in m, mid
            if not m["parked"]:
                assert "persona_suffix" in m, mid

    def test_models_endpoint_advertises_every_mode(self, client, mod):
        r = client.get("/v1/models", headers={"Authorization": f"Bearer {TOKEN}"})
        ids = {d["id"] for d in r.json()["data"]}
        assert ids == set(mod.MODES)

    def test_parked_modes_never_spawn_claude(self, client, mod, monkeypatch):
        """Parked modes must answer instantly — never reach the subprocess path."""
        def boom(*a, **k):
            raise AssertionError("parked mode spawned claude")
        monkeypatch.setattr(mod, "run_claude", boom)
        for mid, m in mod.MODES.items():
            if not m["parked"]:
                continue
            r = client.post("/v1/chat/completions",
                            headers={"Authorization": f"Bearer {TOKEN}"},
                            json={"model": mid, "stream": False,
                                  "messages": [{"role": "user", "content": "hi"}]})
            assert r.status_code == 200, mid
            assert "coming soon" in r.json()["choices"][0]["message"]["content"].lower()


# --------------------------------------------------------------- catalog parsing
class TestCatalog:
    def test_tolerates_ragged_rows(self, mod, tmp_path, monkeypatch):
        tsv = tmp_path / "index.tsv"
        tsv.write_text(
            "slug\tcreated\tupdated\tengine\ttitle\n"
            "full\t2026-01-01\t2026-01-02T10:00\topenscad\tA Full Row\n"
            "short\t2026-01-01\n"          # truncated mid-row
            "\t\t\t\t\n"                   # blank slug -> skipped
            "minimal\n"                    # slug only
        )
        monkeypatch.setattr(mod, "PROJECTS_DIR", tmp_path)
        cat = mod.catalog()
        assert set(cat) == {"full", "short", "minimal"}
        assert cat["full"]["title"] == "A Full Row"
        assert cat["full"]["updated"] == "2026-01-02"   # trimmed to 10 chars
        assert cat["short"]["engine"] == ""             # missing column -> empty
        assert cat["minimal"]["title"] == ""

    def test_missing_file_is_not_an_error(self, mod, tmp_path, monkeypatch):
        monkeypatch.setattr(mod, "PROJECTS_DIR", tmp_path / "nope")
        assert mod.catalog() == {}
