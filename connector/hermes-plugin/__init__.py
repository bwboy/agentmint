"""Hermes plugin entrypoint — wires the Arena platform adapter into the gateway.

This file mirrors the convention used by every built-in Hermes platform plugin
(see plugins/platforms/irc/__init__.py): re-export `register` from `adapter`.
"""
from .adapter import register

__all__ = ["register"]
