"""Installed command-line entry point for AikiMap."""

from __future__ import annotations

import argparse
import sys


def _help_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aikimap",
        description="Launch an AI coding agent with an ambient AikiMap view.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("codex", "claude", "agent", "view"),
        help="codex, claude, a custom agent, or the standalone repository view",
    )
    return parser


def main(arguments: list[str] | None = None) -> int:
    supplied = list(sys.argv[1:] if arguments is None else arguments)
    if not supplied or supplied[0] in {"-h", "--help"}:
        _help_parser().print_help()
        return 0

    command, remainder = supplied[0], supplied[1:]
    if command == "codex":
        from agent_launcher import main as launch_agent

        return launch_agent(["--source", "codex", "--", "codex", *remainder])
    if command == "claude":
        from agent_launcher import main as launch_agent

        return launch_agent(
            ["--source", "claude-code", "--", "claude", *remainder]
        )
    if command == "agent":
        from agent_launcher import main as launch_agent

        return launch_agent(remainder)
    if command == "view":
        from visualizer import main as view_repository

        return view_repository(remainder)

    _help_parser().error(f"unknown command: {command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
