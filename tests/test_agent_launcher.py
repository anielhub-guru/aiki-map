from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from agent_launcher import (
    detect_repository,
    main,
    parse_arguments,
    resolve_agent_command,
    stop_process,
)
from platform_windows import corner_position, primary_screen_size


class AgentLauncherTests(unittest.TestCase):
    def test_detect_repository_returns_worktree_root_from_nested_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(
                ["git", "-C", str(repository), "init", "-q"],
                check=True,
                capture_output=True,
            )
            nested = repository / "src" / "feature"
            nested.mkdir(parents=True)

            self.assertEqual(detect_repository(nested), repository.resolve())

    def test_command_separator_is_removed(self) -> None:
        arguments = parse_arguments(
            ["--source", "codex", "--", "codex", "--model", "example"]
        )

        self.assertEqual(arguments.command, ["codex", "--model", "example"])

    def test_monitor_only_does_not_require_an_agent_command(self) -> None:
        arguments = parse_arguments(["--source", "codex-ide", "--monitor-only"])

        self.assertTrue(arguments.monitor_only)
        self.assertEqual(arguments.command, [])

    def test_detached_ide_launch_returns_without_starting_server(self) -> None:
        with (
            patch("agent_launcher.detect_repository", return_value=Path("/tmp/project")),
            patch("agent_launcher.start_live_server") as server,
            patch("agent_launcher.subprocess.Popen") as spawn,
        ):
            self.assertEqual(
                main(["--source", "codex-ide", "--monitor-only", "--detach"]),
                0,
            )

        server.assert_not_called()
        command = spawn.call_args.args[0]
        self.assertEqual(command[1:5], ["-m", "aikimap_cli", "ide", "--repository"])
        self.assertEqual(command[5], "/tmp/project")
        self.assertTrue(spawn.call_args.kwargs["start_new_session"])

    def test_stop_process_terminates_then_waits(self) -> None:
        process = Mock()
        process.poll.return_value = None
        process.wait.return_value = 0

        self.assertEqual(stop_process(process), 0)

        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=5.0)

    def test_corner_position_stays_visible_on_small_display(self) -> None:
        self.assertEqual(corner_position(400, 300), (20, 20))

    @patch("platform_windows.platform.system", return_value="Darwin")
    def test_macos_screen_size_uses_appkit_without_tk(self, _system) -> None:
        size = type("Size", (), {"width": 1440, "height": 900})()
        screen = type(
            "Screen",
            (),
            {"frame": lambda self: type("Frame", (), {"size": size})()},
        )()
        appkit = type(
            "AppKit",
            (),
            {"NSScreen": type("NSScreen", (), {"mainScreen": lambda: screen})},
        )()
        with patch.dict("sys.modules", {"AppKit": appkit, "tkinter": None}):
            self.assertEqual(primary_screen_size(), (1440, 900))

    @patch("agent_launcher.shutil.which", return_value="/usr/local/bin/codex")
    def test_agent_command_prefers_path_executable(self, _which) -> None:
        command = resolve_agent_command(["codex", "--help"], "codex")

        self.assertEqual(command, ["/usr/local/bin/codex", "--help"])

    @patch("agent_launcher.platform.system", return_value="Darwin")
    @patch("agent_launcher.shutil.which", return_value=None)
    def test_codex_uses_macos_desktop_bundle(self, _which, _system) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "codex"
            executable.write_text("#!/bin/sh\n", encoding="utf-8")
            executable.chmod(0o755)
            with patch("agent_launcher.MACOS_CODEX_CLI", executable):
                command = resolve_agent_command(["codex"], "codex")

        self.assertEqual(command, [str(executable)])

    @patch("agent_launcher.platform.system", return_value="Linux")
    @patch("agent_launcher.shutil.which", return_value=None)
    def test_unknown_custom_command_is_left_for_subprocess_error(
        self,
        _which,
        _system,
    ) -> None:
        command = resolve_agent_command(["custom-agent"], "custom")

        self.assertEqual(command, ["custom-agent"])


if __name__ == "__main__":
    unittest.main()
