"""CLI entrypoint: `python -m agentmint_connector` / `agentmint-connector`."""
import argparse
import asyncio
import logging
import sys

from .config import Config


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agentmint-connector",
        description="AgentMint Connector — bridge a local OpenAI-compatible agent to the platform")
    p.add_argument("--platform-url", help="WebSocket URL (default ws://localhost:8000/ws)")
    p.add_argument("--connector-id", help="Connector ID issued by the platform")
    p.add_argument("--connector-token", help="Connector token (one-shot reveal)")
    p.add_argument("--agent-api-base", help="Local agent OpenAI-compatible base URL")
    p.add_argument("--agent-api-key", help="Bearer key passed to the local agent")
    p.add_argument("--agent-model", help="Model id to request, e.g. gpt-4o-mini")
    p.add_argument("--max-concurrent", type=int, help="Max concurrent answer generations")
    p.add_argument("--agent-type", choices=["openclaw", "hermes"], help="Declared agent type")
    p.add_argument("-v", "--verbose", action="count", default=0, help="-v for INFO, -vv for DEBUG")
    return p.parse_args()


def build_config(args: argparse.Namespace) -> Config:
    cfg = Config()
    # Apply CLI overrides only when explicitly provided.
    overrides = {k: v for k, v in vars(args).items()
                 if v is not None and k not in ("verbose",)}
    if overrides:
        cfg = Config(**{**cfg.model_dump(), **overrides})
    return cfg


def main():
    args = parse_args()
    cfg = build_config(args)

    level = logging.WARNING
    if args.verbose >= 2: level = logging.DEBUG
    elif args.verbose >= 1: level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("agentmint_connector")

    missing = cfg.validate_required()
    if missing:
        log.error("missing required config: %s", ", ".join(missing))
        log.error("set via env or --flag. See `agentmint-connector --help`")
        sys.exit(2)

    log.info("starting %r", cfg)
    # Late import so --help works without optional deps installed
    from .main import run
    try:
        asyncio.run(run(cfg))
    except KeyboardInterrupt:
        log.info("bye")


if __name__ == "__main__":
    main()
