#!/usr/bin/env python3
"""Inspect installed AgentMint Hermes plugin copies.

Run this on the Agent/Hermes machine from the AgentArena repo root:

    python connector/hermes-plugin/check-install.py

It prints the version marker and stale-code indicators for the repo copy and
the common Hermes plugin install locations.
"""
from __future__ import annotations

import os
import re
from pathlib import Path


VERSION_RE = re.compile(r'AGENTMINT_WS_CLIENT_VERSION\s*=\s*"([^"]+)"')
STALE_PATTERNS = {
    "MAX_ATTEMPTS": "old circuit-break constant",
    "retry %d/%d": "old retry log with fixed attempt count",
}


def inspect(path: Path) -> dict[str, str | bool]:
    ws_client = path / "ws_client.py"
    if not ws_client.exists():
        return {"exists": False, "version": "", "stale": "", "target": "", "commit": ""}

    target = ""
    if path.is_symlink():
        target = str(path.resolve())
    text = ws_client.read_text(encoding="utf-8", errors="replace")
    version_match = VERSION_RE.search(text)
    commit_file = path / ".agentmint-plugin-build"
    commit = commit_file.read_text(encoding="utf-8", errors="replace").strip() if commit_file.exists() else ""
    stale = [
        label
        for pattern, label in STALE_PATTERNS.items()
        if pattern in text
    ]
    return {
        "exists": True,
        "version": version_match.group(1) if version_match else "missing",
        "stale": ", ".join(stale),
        "target": target,
        "commit": commit,
    }


def print_row(label: str, path: Path) -> None:
    info = inspect(path)
    print(f"{label}: {path}")
    if not info["exists"]:
        print("  status: missing")
        return
    print(f"  version: {info['version']}")
    if info["commit"]:
        print(f"  installed_commit: {info['commit']}")
    if info["target"]:
        print(f"  symlink_target: {info['target']}")
    print(f"  stale_markers: {info['stale'] or 'none'}")


def main() -> None:
    repo_plugin = Path(__file__).resolve().parent
    cwd = Path.cwd()
    hermes_home = Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()

    candidates = [
        ("repo copy", repo_plugin),
        ("user install", hermes_home / "plugins/platforms/agentmint"),
        ("project install", cwd / ".hermes/plugins/platforms/agentmint"),
    ]
    print(f"HERMES_HOME={hermes_home}")
    for label, path in candidates:
        print_row(label, path)


if __name__ == "__main__":
    main()
