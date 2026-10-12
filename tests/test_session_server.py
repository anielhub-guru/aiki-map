from pathlib import Path
import json
import subprocess
import tempfile
import unittest
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from live_server import LiveApplication, create_server
from session import SessionState
from snapshot_builder import SnapshotBuilder


class SessionServerTests(unittest.TestCase):
    def test_live_document_and_apis_require_token_and_security_headers(self) -> None:
        application = SimpleNamespace(
            close_token="session-secret",
            close_callback=None,
            document=b"<html></html>",
            baseline_payload=b"{}",
            session_payload=lambda: b"{}",
        )
        server = create_server(application)
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        root = f"http://127.0.0.1:{server.server_port}"
        try:
            with self.assertRaises(HTTPError) as error:
                urlopen(f"{root}/", timeout=2)
            self.assertEqual(error.exception.code, 403)

            with urlopen(f"{root}/?token=session-secret", timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers["X-Frame-Options"], "DENY")
                self.assertEqual(
                    response.headers["X-Content-Type-Options"],
                    "nosniff",
                )
                self.assertIn(
                    "frame-ancestors 'none'",
                    response.headers["Content-Security-Policy"],
                )

            with self.assertRaises(HTTPError) as error:
                urlopen(f"{root}/api/session", timeout=2)
            self.assertEqual(error.exception.code, 403)

            request = Request(
                f"{root}/api/session",
                headers={"X-AikiMap-Token": "session-secret"},
            )
            with urlopen(request, timeout=2) as response:
                self.assertEqual(response.status, 200)

            invalid_host = Request(
                f"{root}/api/session",
                headers={
                    "Host": f"attacker.example:{server.server_port}",
                    "X-AikiMap-Token": "session-secret",
                },
            )
            with self.assertRaises(HTTPError) as error:
                urlopen(invalid_host, timeout=2)
            self.assertEqual(error.exception.code, 421)
        finally:
            server.shutdown()
            server.server_close()

    def test_close_endpoint_requires_session_token(self) -> None:
        closed = Event()
        callback = Mock(side_effect=closed.set)
        application = SimpleNamespace(close_token="session-secret", close_callback=callback)
        server = create_server(application)
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = f"http://127.0.0.1:{server.server_port}/api/session/close"
        try:
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(url, method="POST"), timeout=2)
            self.assertEqual(error.exception.code, 403)
            callback.assert_not_called()
            with urlopen(Request(url, method="POST", headers={"X-AikiMap-Token": "session-secret"}), timeout=2) as response:
                self.assertEqual(response.status, 200)
                response.read()
            self.assertTrue(closed.wait(2))
            callback.assert_called_once_with()
        finally:
            server.shutdown()
            server.server_close()

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
