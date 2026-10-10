from unittest.mock import patch
import unittest

import aikimap_cli


class AikiMapCliTests(unittest.TestCase):
    @patch("agent_launcher.main", return_value=0)
    def test_codex_shortcut_passes_agent_arguments(self, launch_agent) -> None:
        result = aikimap_cli.main(["codex", "--model", "example"])

        self.assertEqual(result, 0)
        launch_agent.assert_called_once_with(
            ["--source", "codex", "--", "codex", "--model", "example"]
        )

    @patch("agent_launcher.main", return_value=0)
    def test_claude_shortcut_uses_claude_executable(self, launch_agent) -> None:
        result = aikimap_cli.main(["claude"])

        self.assertEqual(result, 0)
        launch_agent.assert_called_once_with(
            ["--source", "claude-code", "--", "claude"]
        )

    @patch("agent_launcher.main", return_value=0)
    def test_custom_agent_forwards_full_configuration(self, launch_agent) -> None:
        arguments = ["--source", "custom", "--browser", "--", "custom-agent"]

        result = aikimap_cli.main(["agent", *arguments])

        self.assertEqual(result, 0)
        launch_agent.assert_called_once_with(arguments)

    @patch("visualizer.main", return_value=0)
    def test_view_defaults_are_handled_by_visualizer(self, view_repository) -> None:
        result = aikimap_cli.main(["view"])

        self.assertEqual(result, 0)
        view_repository.assert_called_once_with([])


if __name__ == "__main__":
    unittest.main()
