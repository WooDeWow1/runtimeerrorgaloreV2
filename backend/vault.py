"""Owner escape hatch: a code map and a full database export.

Gated by a second secret that lives only in the backend environment, on top of the normal admin
session. Nothing here is reachable without both.
"""
import ast
import os
import secrets
import time
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
CODE_DIRS = [("backend", ["*.py"]), ("frontend/src", ["*.js", "*.jsx"])]
SKIP_DIRS = {"node_modules", "__pycache__", ".git", "build", "dist", "tests", "ui"}
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 900

_attempts: dict[str, list[float]] = {}


def phrase_ok(candidate: str) -> bool:
    expected = os.environ["VAULT_PHRASE"]
    return secrets.compare_digest(candidate.strip(), expected)


def throttled(ip: str) -> bool:
    """Brute forcing a 24 character phrase is hopeless, but rate limit it anyway."""
    now = time.time()
    recent = [t for t in _attempts.get(ip, []) if now - t < LOCKOUT_SECONDS]
    _attempts[ip] = recent
    return len(recent) >= MAX_ATTEMPTS


def record_failure(ip: str) -> None:
    _attempts.setdefault(ip, []).append(time.time())


def clear_failures(ip: str) -> None:
    _attempts.pop(ip, None)


def _py_outline(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    lines = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = (ast.get_docstring(node) or "").split("\n")[0]
            lines.append(f"- `{node.name}()`{' — ' + doc if doc else ''}")
        elif isinstance(node, ast.ClassDef):
            methods = [n.name for n in node.body
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            suffix = f" · methods: {', '.join(methods)}" if methods else ""
            lines.append(f"- `class {node.name}`{suffix}")
    return lines


def _js_outline(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith(("export const ", "export function ", "export default function ",
                            "const ", "function ")) and ("=>" in line or "function" in line):
            name = line.split("(")[0].replace("export default function", "").replace(
                "export function", "").replace("export const", "").replace(
                "function", "").replace("const", "").split("=")[0].strip()
            if name and name[0].isalpha() and len(name) < 40:
                lines.append(f"- `{name}`")
    return lines[:40]


def _walk(root: Path, patterns: list[str]) -> list[Path]:
    found: list[Path] = []
    for pattern in patterns:
        for path in sorted(root.rglob(pattern)):
            if not any(part in SKIP_DIRS for part in path.parts):
                found.append(path)
    return found


def code_map() -> str:
    """A single markdown guide: every source file, what it holds, and how it is wired."""
    from datetime import datetime, timezone

    out = [
        "# PokeCoins — Code Map",
        "",
        f"Generated {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')}",
        "",
        "Stack: React 19 (CRA + craco) · FastAPI · MongoDB. Backend serves every route under",
        "`/api` on port 8001; the frontend talks to it via `REACT_APP_BACKEND_URL`.",
        "",
        "Third-party services, all keyed from `backend/.env`: SellAuth (checkout, catalog,",
        "affiliate program), Emergent managed email, Cloudflare Turnstile, ip-api.com.",
        "",
    ]

    for label, patterns in (("backend", ["*.py"]), ("frontend/src", ["*.js", "*.jsx"])):
        root = APP_ROOT / label
        if not root.exists():
            continue
        out += [f"## {label}", ""]
        for path in _walk(root, patterns):
            rel = path.relative_to(APP_ROOT)
            outline = _py_outline(path) if path.suffix == ".py" else _js_outline(path)
            size = path.stat().st_size // 1024
            out += [f"### `{rel}` ({size} KB)", ""]
            out += outline or ["- (no top level definitions)"]
            out += [""]

    return "\n".join(out)
