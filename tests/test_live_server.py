from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from live_server import LiveApplication
from snapshot_builder import SnapshotBuilder


class LiveServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary_directory.name)
        self._git("init", "-q")
        self._git("config", "user.name", "Aiki Map Test")
        self._git("config", "user.email", "test@example.com")
        (self.repository / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
        self._git("add", "app.py")
        self._git("commit", "-q", "-m", "Initial commit")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_unchanged_client_version_returns_no_payload(self) -> None:
        application = LiveApplication(SnapshotBuilder(self.repository))

        self.assertIsNone(application.state_payload(application.initial_version))

    def test_changed_working_tree_returns_new_payload_without_changing_git(self) -> None:
        application = LiveApplication(SnapshotBuilder(self.repository))
        (self.repository / "unexpected.py").write_text(
            "UNEXPECTED = True\n",
            encoding="utf-8",
        )
        status_before = self._status()

        payload = application.state_payload(application.initial_version)

        self.assertIsNotNone(payload)
        state = json.loads(payload)
        self.assertEqual(state["snapshots"][0]["key"], "1 file")
        self.assertEqual(state["snapshots"][0]["detail"], "")
        self.assertNotEqual(state["version"], application.initial_version)
        self.assertEqual(self._status(), status_before)

    def test_new_commit_refreshes_history(self) -> None:
        builder = SnapshotBuilder(self.repository)
        initial_head = builder.load()[1].commit.full_hash
        (self.repository / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        self._git("add", "app.py")
        self._git("commit", "-q", "-m", "Update value")

        snapshots = builder.load()

        self.assertNotEqual(snapshots[1].commit.full_hash, initial_head)
        self.assertEqual(snapshots[1].commit.message, "Update value")
        self.assertEqual(snapshots[0].change_count, 0)

    def _git(self, *arguments: str) -> None:
        subprocess.run(
            ["git", "-C", str(self.repository), *arguments],
            check=True,
            capture_output=True,
        )

    def _status(self) -> bytes:
        return subprocess.run(
            [
                "git",
                "-C",
                str(self.repository),
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
                "--renames",
            ],
            check=True,
            capture_output=True,
        ).stdout


if __name__ == "__main__":
    unittest.main()
