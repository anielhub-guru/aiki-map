from pathlib import Path
import unittest

from session import SessionPhase, SessionState


class SessionStateTests(unittest.TestCase):
    def test_lifecycle_is_monotonic(self) -> None:
        session = SessionState(Path.cwd(), "codex")

        self.assertEqual(session.snapshot().phase, SessionPhase.STARTED)
        session.mark_active()
        self.assertEqual(session.snapshot().phase, SessionPhase.ACTIVE)
        session.mark_stopped("Agent process exited", 0)
        stopped = session.snapshot()
        self.assertEqual(stopped.phase, SessionPhase.STOPPED)
        self.assertEqual(stopped.exit_code, 0)
        self.assertIsNotNone(stopped.stopped_at)
        session.dismiss()
        session.mark_active()
        self.assertEqual(session.snapshot().phase, SessionPhase.STOPPED)


if __name__ == "__main__":
    unittest.main()
