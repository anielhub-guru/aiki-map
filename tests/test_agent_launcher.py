from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from agent_launcher import detect_repository, parse_arguments, resolve_agent_command
from platform_windows import corner_position


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

    def test_corner_position_stays_visible_on_small_display(self) -> None:
        self.assertEqual(corner_position(400, 300), (20, 20))

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
