"""Launch an AI coding agent with an ambient, read-only AikiMap session."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from threading import Thread
from time import sleep

from corner_window import WindowActions, show_corner_window
from git_reader import GitRepositoryError, validate_repository
from live_server import start_live_server
from session import SessionState
from snapshot_builder import SnapshotBuilder


COMMIT_LIMIT = 10
MACOS_CODEX_CLI = Path(
    "/Applications/ChatGPT.app/Contents/Resources/codex-cli/"
    "CodexCLI.app/Contents/MacOS/codex"
)


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch an agent and show its repository activity in AikiMap."
    )
    parser.add_argument("--source", required=True, help="Agent name, such as codex")
    parser.add_argument(
        "--repository",
        default=".",
        help="Repository or a directory inside it; defaults to the current directory",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Use the default browser instead of the native corner window",
    )
    parser.add_argument(
        "--monitor-only",
        action="store_true",
        help="Monitor the repository without launching an agent process",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Agent command, normally placed after --",
    )
    parsed = parser.parse_args(arguments)
    if parsed.command[:1] == ["--"]:
        parsed.command = parsed.command[1:]
    if not parsed.command and not parsed.monitor_only:
        parser.error("an agent command is required after --")
    return parsed


def detect_repository(start: str | Path) -> Path:
    """Resolve the Git worktree root using a read-only command."""
    candidate = Path(start).expanduser().resolve()
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    result = subprocess.run(
        ["git", "-C", str(candidate), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or f"Not a Git repository: {candidate}"
        raise GitRepositoryError(message)
    return validate_repository(result.stdout.strip())


def resolve_agent_command(command: list[str], source: str) -> list[str]:
    """Resolve supported desktop-bundled CLIs before starting the agent."""
    executable = command[0]
    discovered = shutil.which(executable)
    if discovered is not None:
        return [discovered, *command[1:]]

    if source == "codex" and executable == "codex" and platform.system() == "Darwin":
        if MACOS_CODEX_CLI.is_file() and os.access(MACOS_CODEX_CLI, os.X_OK):
            return [str(MACOS_CODEX_CLI), *command[1:]]

    return command


def stop_process(process: subprocess.Popen[bytes], timeout: float = 5.0) -> int:
    """Stop a wrapped agent outside the native webview callback thread."""
    if process.poll() is not None:
        return process.returncode or 0
    process.terminate()
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.wait()


def main(arguments: list[str] | None = None) -> int:
    options = parse_arguments(arguments)
    try:
        repository = detect_repository(options.repository)
        session = SessionState(repository, options.source)
        builder = SnapshotBuilder(repository, commit_limit=COMMIT_LIMIT)
        application, server, url = start_live_server(builder, session)
    except (GitRepositoryError, OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    process: subprocess.Popen[bytes] | None = None
    if not options.monitor_only:
        try:
            resolved_command = resolve_agent_command(options.command, options.source)
            process = subprocess.Popen(resolved_command)
        except OSError as error:
            server.shutdown()
            server.server_close()
            hint = ""
            if options.source == "codex" and options.command[0] == "codex":
                hint = " Install the Codex CLI or launch Codex once from the desktop app."
            print(
                f"Error: could not start {options.command[0]}: {error}.{hint}",
                file=sys.stderr,
            )
            return 1

    session.mark_active()

    if process is not None:
        def watch_agent() -> None:
            exit_code = process.wait()
            session.mark_stopped("Agent process exited", exit_code)

        watcher = Thread(target=watch_agent, daemon=True)
        watcher.start()
    actions = WindowActions(process, session)

    try:
        native_window = show_corner_window(url, actions, options.browser)
        if not native_window:
            print(url)
            print("Browser fallback active; press Ctrl+C to stop monitoring.")
            while process is None or process.poll() is None:
                sleep(0.25)
            while True:
                sleep(1)
        elif (
            process is not None
            and not actions.shutdown_requested.is_set()
            and process.poll() is None
        ):
            process.wait()
    except KeyboardInterrupt:
        session.mark_stopped("Interrupted by user")
    finally:
        if process is not None and process.poll() is None:
            stop_process(process)
        server.shutdown()
        server.server_close()

    if process is None or actions.shutdown_requested.is_set():
        return 0
    return process.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
