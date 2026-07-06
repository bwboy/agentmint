#!/usr/bin/env python3
"""Configure Hermes for the AgentMint platform plugin."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write AgentMint settings into Hermes config.yaml")
    parser.add_argument("--connector-id", required=True, help="AgentMint connector id, e.g. conn_xxxxxxxx")
    parser.add_argument("--connector-token", required=True, help="AgentMint connector token, e.g. conn_sk_...")
    parser.add_argument("--platform-url", default="ws://localhost:8000/ws", help="Arena WebSocket URL")
    parser.add_argument("--hermes-home", default=os.environ.get("HERMES_HOME", "~/.hermes"), help="Hermes home directory")
    parser.add_argument("--config", default=os.environ.get("HERMES_CONFIG", ""), help="Explicit Hermes config path")
    parser.add_argument("--queue-db", default="", help="Optional AgentMint queue DB path")
    parser.add_argument("--max-concurrent", type=int, default=3, help="Max concurrent AgentMint questions")
    parser.add_argument("--usage-wait-seconds", type=float, default=1.0, help="Seconds to wait for Hermes usage metadata")
    parser.add_argument("--debug-usage", action="store_true", help="Enable usage capture debug logs")
    parser.add_argument(
        "--permission-profile",
        choices=("strict", "balanced", "expanded"),
        default="balanced",
        help="Local Hermes permission profile for AgentMint tasks. Does not disable approvals.",
    )
    parser.add_argument("--skip-enable", action="store_true", help="Do not call `hermes plugins enable platforms/agentmint`")
    return parser.parse_args()


def load_yaml_module():
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "PyYAML is required to edit config.yaml safely. Install it in this Python environment, "
            "or edit ~/.hermes/config.yaml manually from connector/hermes-plugin/README.md."
        ) from exc
    return yaml


def config_path(args: argparse.Namespace) -> Path:
    if args.config:
        return Path(args.config).expanduser()
    return Path(args.hermes_home).expanduser() / "config.yaml"


def backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    backup_path = path.with_suffix(path.suffix + f".backup.{datetime.now().strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(path, backup_path)
    return backup_path


def ensure_mapping(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def permission_allowlist(profile: str) -> list[str]:
    if profile == "expanded":
        return ["python", "python3"]
    if profile == "balanced":
        return ["python", "python3"]
    return []


def merge_list(existing: Any, additions: list[str]) -> list[str]:
    values = existing if isinstance(existing, list) else []
    merged: list[str] = []
    for value in [*values, *additions]:
        if not isinstance(value, str) or not value.strip():
            continue
        if value not in merged:
            merged.append(value)
    return merged


def configure(data: dict, args: argparse.Namespace) -> dict:
    plugins = ensure_mapping(data.get("plugins"))
    enabled = plugins.get("enabled")
    if not isinstance(enabled, list):
        enabled = []
    if "platforms/agentmint" not in enabled:
        enabled.append("platforms/agentmint")
    plugins["enabled"] = enabled
    data["plugins"] = plugins

    gateway = ensure_mapping(data.get("gateway"))
    platforms = ensure_mapping(gateway.get("platforms"))
    agentmint = ensure_mapping(platforms.get("agentmint"))
    extra = ensure_mapping(agentmint.get("extra"))

    agentmint["enabled"] = True
    agentmint["home_channel"] = {
        "platform": "agentmint",
        "chat_id": "agentmint-home",
        "name": "AgentMint",
    }
    extra["connector_id"] = args.connector_id
    extra["connector_token"] = args.connector_token
    extra["platform_url"] = args.platform_url
    extra["max_concurrent"] = args.max_concurrent
    extra["usage_wait_seconds"] = args.usage_wait_seconds
    extra["debug_usage"] = bool(args.debug_usage)
    extra["permission_profile"] = args.permission_profile
    if args.queue_db:
        extra["queue_db"] = args.queue_db

    agentmint["extra"] = extra
    platforms["agentmint"] = agentmint
    gateway["platforms"] = platforms
    data["gateway"] = gateway
    data["command_allowlist"] = merge_list(
        data.get("command_allowlist"),
        permission_allowlist(args.permission_profile),
    )
    return data


def maybe_enable_plugin(skip: bool) -> None:
    if skip:
        return
    hermes = shutil.which("hermes")
    if not hermes:
        print("hermes command not found; skipped `hermes plugins enable platforms/agentmint`")
        return
    subprocess.run([hermes, "plugins", "enable", "platforms/agentmint"], check=False)


def main() -> None:
    args = parse_args()
    yaml = load_yaml_module()
    path = config_path(args)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    if existing is None:
        existing = {}
    if not isinstance(existing, dict):
        raise SystemExit(f"{path} must contain a YAML mapping at the top level")

    backup_path = backup(path)
    updated = configure(existing, args)
    path.write_text(yaml.safe_dump(updated, allow_unicode=True, sort_keys=False), encoding="utf-8")

    print(f"Wrote AgentMint config to {path}")
    if backup_path:
        print(f"Backup: {backup_path}")
    maybe_enable_plugin(args.skip_enable)
    print("Next: restart `hermes gateway`")


if __name__ == "__main__":
    main()
