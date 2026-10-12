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

    def test_rendered_diff_split_keeps_javascript_newline_literal(self) -> None:
        application = LiveApplication(SnapshotBuilder(self.repository))

        self.assertIn(b'content.split("\\n")', application.document)
        self.assertNotIn(b'content.split("\n")', application.document)

    def test_rendered_page_supports_ambient_and_review_modes(self) -> None:
        application = LiveApplication(SnapshotBuilder(self.repository))

        self.assertIn(b'id="aikimap-session-controls-slot"', application.document)
        self.assertIn(
            b'class="window-drag-region pywebview-drag-region"',
            application.document,
        )
        self.assertIn(b"window.aikimapSetDisplayMode", application.document)
        self.assertIn(b"body.ambient-mode .legend", application.document)
        self.assertLess(
            application.document.index(b'class="chart-shell"'),
            application.document.index(b'class="legend"'),
        )
        self.assertIn(b'id="session-indicator"', application.document)
        self.assertIn(b'id="activity-status"', application.document)
        self.assertIn(b"EDITING", application.document)
        self.assertIn(b'activity.paths.join("\\n")', application.document)

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

    def test_repeated_edit_of_modified_file_emits_fresh_activity(self) -> None:
        application = LiveApplication(SnapshotBuilder(self.repository))
        (self.repository / "app.py").write_text("VALUE = 20\n", encoding="utf-8")
        first = json.loads(application.state_payload(application.initial_version))

        (self.repository / "app.py").write_text(
            "VALUE = 200\nEXTRA = True\n",
            encoding="utf-8",
        )
        second_payload = application.state_payload(first["version"])

        self.assertIsNotNone(second_payload)
        second = json.loads(second_payload)
        self.assertEqual(second["activity"]["paths"], ["app.py"])
        self.assertGreater(
            second["activity"]["revision"],
            first["activity"]["revision"],
        )
        self.assertIn("● app.py", second["traces"][0]["labels"])

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

    def test_file_details_separate_staged_and_unstaged_diff(self) -> None:
        builder = SnapshotBuilder(self.repository)
        application = LiveApplication(builder)
        (self.repository / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        self._git("add", "app.py")
        (self.repository / "app.py").write_text(
            "VALUE = 2\nEXTRA = True\n",
            encoding="utf-8",
        )
        status_before = self._status()
        revision = builder.load()[0].commit.full_hash

        summary = json.loads(
            application.file_payload("working", revision, "app.py", False)
        )
        details = json.loads(
            application.file_payload("working", revision, "app.py", True)
        )

        self.assertEqual(
            summary["state"],
            "Staged modification + Unstaged modification",
        )
        self.assertEqual((summary["additions"], summary["deletions"]), (2, 1))
        self.assertEqual(
            [section["label"] for section in details["sections"]],
            ["Staged changes", "Unstaged changes"],
        )
        self.assertEqual(self._status(), status_before)

    def test_untracked_file_diff_and_unsafe_path_rejection(self) -> None:
        builder = SnapshotBuilder(self.repository)
        application = LiveApplication(builder)
        (self.repository / "new.py").write_text("NEW = True\n", encoding="utf-8")
        revision = builder.load()[0].commit.full_hash

        details = json.loads(
            application.file_payload("working", revision, "new.py", True)
        )

        self.assertEqual(details["state"], "Untracked")
        self.assertEqual((details["additions"], details["deletions"]), (1, 0))
        self.assertEqual(details["sections"][0]["label"], "Untracked file")
        with self.assertRaises(ValueError):
            application.file_payload("working", revision, "../outside.py", True)

    def test_commit_diff_and_binary_summary(self) -> None:
        builder = SnapshotBuilder(self.repository)
        application = LiveApplication(builder)
        initial_commit = builder.load()[1].commit.full_hash
        commit_details = json.loads(
            application.file_payload("commit", initial_commit, "app.py", True)
        )
        self.assertEqual(
            commit_details["comparison"],
            f"Changes introduced by commit {initial_commit[:7]}",
        )
        self.assertEqual(commit_details["sections"][0]["label"], "Committed changes")

        (self.repository / "asset.bin").write_bytes(b"\x00one")
        self._git("add", "asset.bin")
        self._git("commit", "-q", "-m", "Add binary asset")
        binary_builder = SnapshotBuilder(self.repository)
        binary_application = LiveApplication(binary_builder)
        (self.repository / "asset.bin").write_bytes(b"\x00two")
        revision = binary_builder.load()[0].commit.full_hash
        binary_details = json.loads(
            binary_application.file_payload(
                "working",
                revision,
                "asset.bin",
                False,
            )
        )
        self.assertTrue(binary_details["binary"])

    def test_renamed_file_details_include_previous_path(self) -> None:
        self._git("mv", "app.py", "renamed.py")
        builder = SnapshotBuilder(self.repository)
        application = LiveApplication(builder)
        revision = builder.load()[0].commit.full_hash

        details = json.loads(
            application.file_payload("working", revision, "renamed.py", True)
        )

        self.assertEqual(details["state"], "Staged rename")
        self.assertEqual(details["previousPath"], "app.py")
        self.assertEqual(details["sections"][0]["label"], "Staged changes")

    def test_large_diff_is_truncated(self) -> None:
        large_content = "".join(f"line {index}\n" for index in range(2_100))
        (self.repository / "large.txt").write_text(large_content, encoding="utf-8")
        builder = SnapshotBuilder(self.repository)
        application = LiveApplication(builder)
        revision = builder.load()[0].commit.full_hash

        details = json.loads(
            application.file_payload("working", revision, "large.txt", True)
        )

        self.assertTrue(details["truncated"])
        rendered_lines = sum(
            len(section["content"].splitlines())
            for section in details["sections"]
        )
        self.assertLessEqual(rendered_lines, 2_000)

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
