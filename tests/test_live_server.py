from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from git_reader import get_branches
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
            b'class="brand-row pywebview-drag-region"',
            application.document,
        )
        self.assertIn(b"window.aikimapSetDisplayMode", application.document)
        self.assertIn(b"body.ambient-mode .legend", application.document)
        self.assertIn(
            b'grid-template-areas: "header" "activity" "map" "legend"',
            application.document,
        )
        self.assertLess(
            application.document.index(b'class="chart-shell"'),
            application.document.index(b'class="legend"'),
        )
        self.assertIn(b'id="session-indicator"', application.document)
        self.assertIn(b'id="activity-status"', application.document)
        self.assertIn(b"EDITING", application.document)
        self.assertIn(b"View file", application.document)
        self.assertIn(b'activity.paths.join("\\n")', application.document)
        self.assertIn(b'id="activity-robots"', application.document)
        self.assertIn(b'activityRobots,\n          "activity-robot"', application.document)
        self.assertIn(b'id="review-robots"', application.document)
        self.assertIn(b'reviewRobots,\n          "change-pulse-robot"', application.document)
        self.assertIn(b"function scheduleChangePulse()", application.document)
        self.assertIn(b"await Plotly.restyle", application.document)
        self.assertIn(b"request !== snapshotRequest", application.document)
        self.assertIn(b"candidateAnchorIds(changedPaths, topLevelOnly)", application.document)
        self.assertIn(b"candidateIds && !candidateIds.has(id)", application.document)
        self.assertIn(b"request !== changePulseRequest", application.document)
        self.assertIn(b"reviewRobots.replaceChildren()", application.document)
        self.assertIn(b"opacity: 1; scale: .72", application.document)
        self.assertIn(b"changePulseResizeTimer", application.document)
        self.assertIn(b"setTimeout(scheduleChangePulse, 160)", application.document)
        self.assertNotIn(b"changePulseRequest += 1", application.document)
        self.assertIn(b"AikiBot Change Pulse", application.document)
        self.assertIn(b"MAX_CHANGE_PULSE_ROBOTS = 24", application.document)
        self.assertIn(b'item?.[4] === "file" && item?.[1] !== "unchanged"', application.document)
        self.assertIn(b"if (selectBranchTip) scheduleChangePulse()", application.document)
        self.assertIn(b"pointer-events: none", application.document)
        self.assertIn(b'candidates.push(`dir:${parts.join("/")}`)', application.document)
        self.assertIn(b'paths.join("\\n")', application.document)
        self.assertIn(b'id="file-inspector-back"', application.document)
        self.assertIn(b'id="history-branch-control"', application.document)
        self.assertIn(
            b'headers.set("X-AikiMap-Token", sessionToken)',
            application.document,
        )
        self.assertIn(
            b"branchControl.hidden = selectableBranches.length === 0",
            application.document,
        )
        self.assertIn(b"window.history.pushState", application.document)
        self.assertIn(b'window.addEventListener("popstate"', application.document)

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

    def test_only_current_branch_is_not_offered_as_history(self) -> None:
        application = LiveApplication(SnapshotBuilder(self.repository))

        state = json.loads(application.state_payload("outdated"))

        self.assertEqual(len(state["branches"]), 1)
        self.assertFalse(state["branches"][0]["selectable"])

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

    def test_live_signatures_track_only_changed_files_and_detect_deletion(self) -> None:
        builder = SnapshotBuilder(self.repository)

        initial = builder.load()
        self.assertEqual(builder._working_signatures, {})
        self.assertEqual(initial[0].activity_paths, ())
        cached = builder.load()
        self.assertIs(cached[0].nodes, initial[0].nodes)

        (self.repository / "app.py").unlink()
        deleted = builder.load()

        self.assertEqual(builder._working_signatures, {"app.py": None})
        self.assertEqual(deleted[0].activity_paths, ("app.py",))
        self.assertIsNot(deleted[0].nodes, initial[0].nodes)

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

    def test_branch_history_and_diff_do_not_switch_working_tree(self) -> None:
        current = subprocess.run(
            ["git", "-C", str(self.repository), "rev-parse", "--abbrev-ref", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        self._git("checkout", "-q", "-b", "feature/map")
        (self.repository / "feature.py").write_text("FEATURE = True\n", encoding="utf-8")
        self._git("add", "feature.py")
        self._git("commit", "-q", "-m", "Add feature file")
        self._git("update-ref", "refs/remotes/origin/feature/map", "HEAD")
        self._git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/feature/map")
        self._git("checkout", "-q", current)
        application = LiveApplication(SnapshotBuilder(self.repository))
        before = self._status()

        payload = json.loads(application.state_payload(application.initial_version, "refs/heads/feature/map"))

        self.assertEqual(payload["historyRef"], "refs/heads/feature/map")
        self.assertEqual(payload["snapshots"][1]["message"], "Add feature file")
        self.assertIn("feature.py", payload["traces"][1]["labels"])
        self.assertNotIn("feature.py", payload["traces"][0]["labels"])
        self.assertEqual([branch["name"] for branch in payload["branches"] if branch["current"]], [current])
        self.assertIn("origin/feature/map", [branch["name"] for branch in payload["branches"]])
        self.assertNotIn("origin/HEAD", [branch["name"] for branch in payload["branches"]])
        self.assertIn(
            "feature/map",
            [branch["name"] for branch in payload["branches"] if branch["selectable"]],
        )
        self.assertNotIn(
            "origin/feature/map",
            [branch["name"] for branch in payload["branches"] if branch["selectable"]],
        )
        details = json.loads(application.file_payload(
            "commit", payload["snapshots"][1]["revision"], "feature.py", True,
            "refs/heads/feature/map",
        ))
        self.assertEqual(details["additions"], 1)
        self.assertEqual(self._status(), before)
        self.assertFalse((self.repository / "feature.py").exists())

    def test_new_and_deleted_branches_refresh_metadata(self) -> None:
        application = LiveApplication(SnapshotBuilder(self.repository))
        self._git("branch", "feature/new")
        payload = json.loads(application.state_payload(application.initial_version))
        self.assertIn("feature/new", [branch["name"] for branch in payload["branches"]])
        self._git("branch", "-D", "feature/new")
        updated = json.loads(application.state_payload(payload["version"], "refs/heads/feature/new"))
        self.assertEqual(updated["historyRef"], "")
        self.assertNotIn("feature/new", [branch["name"] for branch in updated["branches"]])

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

    def test_diff_subprocess_output_is_bounded_before_rendering(self) -> None:
        (self.repository / "huge.txt").write_text(
            f"{'x' * 300_000}\n",
            encoding="utf-8",
        )
        builder = SnapshotBuilder(self.repository)
        application = LiveApplication(builder)
        revision = builder.load()[0].commit.full_hash

        details = json.loads(
            application.file_payload("working", revision, "huge.txt", True)
        )

        self.assertTrue(details["truncated"])
        rendered_bytes = sum(
            len(section["content"].encode("utf-8"))
            for section in details["sections"]
        )
        self.assertLessEqual(rendered_bytes, 200_000)

    def test_git_commands_disable_repository_fsmonitor(self) -> None:
        completed = Mock(returncode=0, stdout="", stderr="")
        with patch("git_reader.subprocess.run", return_value=completed) as run:
            get_branches(self.repository)

        command = run.call_args.args[0]
        self.assertEqual(command[1:4], ["-c", "core.fsmonitor=false", "-C"])

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
