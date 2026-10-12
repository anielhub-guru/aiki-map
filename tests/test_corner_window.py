from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from corner_window import WindowActions, show_corner_window
from session import SessionState


class FakeProcess:
    def __init__(self) -> None:
        self.terminated = False

    def poll(self) -> None:
        return None

    def terminate(self) -> None:
        self.terminated = True


class FakeWindow:
    def __init__(self) -> None:
        self.size: tuple[int, int] | None = None
        self.position: tuple[int, int] | None = None
        self.destroyed = False

    def resize(self, width: int, height: int) -> None:
        self.size = (width, height)

    def move(self, x: int, y: int) -> None:
        self.position = (x, y)

    def destroy(self) -> None:
        self.destroyed = True


class FakeEvent:
    def __iadd__(self, _callback: object) -> "FakeEvent":
        return self


class WindowActionsTests(unittest.TestCase):
    def test_review_expands_and_centres_window(self) -> None:
        actions = WindowActions(
            FakeProcess(),
            SessionState(Path.cwd(), "codex"),
        )
        window = FakeWindow()
        actions.attach_window(window, (1440, 900))

        actions.review()

        self.assertEqual(window.size, (1000, 760))
        self.assertEqual(window.position, (220, 70))

    def test_corner_window_is_frameless_without_global_dragging(self) -> None:
        captured: dict[str, object] = {}
        window = SimpleNamespace(
            events=SimpleNamespace(loaded=FakeEvent(), closed=FakeEvent()),
        )

        def create_window(*_arguments: object, **options: object) -> object:
            captured.update(options)
            return window

        webview = SimpleNamespace(create_window=create_window, start=lambda: None)
        actions = WindowActions(FakeProcess(), SessionState(Path.cwd(), "codex"))
        with (
            patch.dict("sys.modules", {"webview": webview}),
            patch("corner_window.primary_screen_size", return_value=None),
        ):
            self.assertTrue(show_corner_window("http://127.0.0.1", actions, False))

        self.assertIs(captured["frameless"], True)
        self.assertIs(captured["easy_drag"], False)

    def test_end_requests_shutdown_without_terminating_from_webview(self) -> None:
        process = FakeProcess()
        session = SessionState(Path.cwd(), "codex")
        actions = WindowActions(process, session)
        window = FakeWindow()
        actions.attach_window(window, None)

        actions.end_session()

        self.assertTrue(actions.shutdown_requested.is_set())
        self.assertTrue(window.destroyed)
        self.assertFalse(process.terminated)
        self.assertEqual(session.snapshot().stop_reason, "Ended by user")


if __name__ == "__main__":
    unittest.main()
