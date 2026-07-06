#!/usr/bin/env python3
"""Inspect or apply local Hermes permission settings for AgentMint."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import configure as agentmint_configure


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage AgentMint Hermes permission profile")
    parser.add_argument("action", choices=("doctor", "apply"), help="doctor prints current status; apply writes the profile")
    parser.add_argument("--profile", choices=("strict", "balanced", "expanded"), default="balanced")
    parser.add_argument("--hermes-home", default=os.environ.get("HERMES_HOME", "~/.hermes"))
    parser.add_argument("--config", default=os.environ.get("HERMES_CONFIG", ""))
    return parser.parse_args()


def config_path(args: argparse.Namespace) -> Path:
    if args.config:
        return Path(args.config).expanduser()
    return Path(args.hermes_home).expanduser() / "config.yaml"


def load_config(path: Path) -> tuple[object, dict]:
    yaml = agentmint_configure.load_yaml_module()
    existing = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    if existing is None:
        existing = {}
    if not isinstance(existing, dict):
        raise SystemExit(f"{path} must contain a YAML mapping at the top level")
    return yaml, existing


def apply_profile(data: dict, profile: str) -> dict:
    data["command_allowlist"] = agentmint_configure.merge_list(
        data.get("command_allowlist"),
        agentmint_configure.permission_allowlist(profile),
    )
    gateway = agentmint_configure.ensure_mapping(data.get("gateway"))
    platforms = agentmint_configure.ensure_mapping(gateway.get("platforms"))
    agentmint = agentmint_configure.ensure_mapping(platforms.get("agentmint"))
    extra = agentmint_configure.ensure_mapping(agentmint.get("extra"))
    extra["permission_profile"] = profile
    agentmint["extra"] = extra
    platforms["agentmint"] = agentmint
    gateway["platforms"] = platforms
    data["gateway"] = gateway
    return data


def print_status(path: Path, data: dict) -> None:
    agentmint = (
        data.get("gateway", {})
        .get("platforms", {})
        .get("agentmint", {})
    )
    extra = agentmint.get("extra", {}) if isinstance(agentmint, dict) else {}
    approvals = data.get("approvals", {}) if isinstance(data.get("approvals"), dict) else {}
    allowlist = data.get("command_allowlist") if isinstance(data.get("command_allowlist"), list) else []
    print(f"config: {path}")
    print(f"agentmint.enabled: {bool(agentmint.get('enabled')) if isinstance(agentmint, dict) else False}")
    print(f"permission_profile: {extra.get('permission_profile', 'missing')}")
    print(f"approvals.mode: {approvals.get('mode', 'default')}")
    print(f"command_allowlist: {', '.join(allowlist) if allowlist else 'empty'}")
    if approvals.get("mode") == "off":
        print("warning: approvals.mode=off disables most Hermes approval prompts; AgentMint does not recommend this.")


def main() -> None:
    args = parse_args()
    path = config_path(args)
    yaml, data = load_config(path)
    if args.action == "doctor":
        print_status(path, data)
        return

    backup = agentmint_configure.backup(path)
    updated = apply_profile(data, args.profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(updated, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"Applied AgentMint permission profile '{args.profile}' to {path}")
    if backup:
        print(f"Backup: {backup}")
    print("Next: restart `hermes gateway`")


if __name__ == "__main__":
    main()
