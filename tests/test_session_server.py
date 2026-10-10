from pathlib import Path
import json
import subprocess
import tempfile
import unittest

from live_server import LiveApplication
from session import SessionState
from snapshot_builder import SnapshotBuilder


class SessionServerTests(unittest.TestCase):
    def test_session_payload_reports_agent_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(
                ["git", "-C", str(repository), "init", "-q"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(repository), "config", "user.name", "Test"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(repository), "config", "user.email", "test@example.com"],
                check=True,
                capture_output=True,
            )
            (repository / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(repository), "add", "app.py"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(repository), "commit", "-q", "-m", "Initial"],
                check=True,
                capture_output=True,
            )
            session = SessionState(repository, "codex")
            application = LiveApplication(SnapshotBuilder(repository), session)

            session.mark_active()
            payload = json.loads(application.session_payload())

            self.assertEqual(payload["phase"], "active")
            self.assertEqual(payload["source"], "codex")
            baseline = json.loads(application.baseline_payload)
            self.assertEqual(payload["baselineVersion"], baseline["version"])


if __name__ == "__main__":
    unittest.main()
