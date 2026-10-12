"""Display AikiMap in a compact native webview with a browser fallback."""

from __future__ import annotations

import subprocess
from threading import Event
from typing import Any
import webbrowser

from platform_windows import (
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    corner_position,
    primary_screen_size,
)
from session import SessionState


_CONTROL_SCRIPT = r"""
(() => {
  if (document.getElementById('aikimap-session-controls')) return;
  const slot = document.getElementById('aikimap-session-controls-slot');
  if (!slot) return;
  const controls = document.createElement('nav');
  controls.id = 'aikimap-session-controls';
  controls.className = 'session-toolbar';
  controls.setAttribute('aria-label', 'Agent session');
  controls.innerHTML = `
    <button id="aikimap-hide" type="button">Hide</button>
    <button id="aikimap-review" type="button">Review</button>
    <button class="end-session" id="aikimap-end" type="button">End</button>
  `;
  slot.appendChild(controls);
  document.getElementById('aikimap-hide').onclick = () => window.pywebview.api.hide();
  document.getElementById('aikimap-review').onclick = async event => {
    await window.pywebview.api.review();
    window.aikimapSetDisplayMode?.('review');
    event.currentTarget.hidden = true;
  };
  document.getElementById('aikimap-end').onclick = () => {
    if (window.confirm('End the wrapped agent session?')) window.pywebview.api.end_session();
  };
  window.aikimapSetDisplayMode?.('ambient');
})();
"""


class WindowActions:
    """Methods exposed only to the local native AikiMap webview."""

    def __init__(
        self,
        process: subprocess.Popen[bytes] | None,
        session: SessionState,
    ) -> None:
        self.process = process
        self.session = session
        self.window: Any = None
        self.screen_size: tuple[int, int] | None = None
        self.shutdown_requested = Event()

    def attach_window(
        self,
        window: Any,
        screen_size: tuple[int, int] | None,
    ) -> None:
        self.window = window
        self.screen_size = screen_size

    def hide(self) -> None:
        if self.window is not None:
            self.window.minimize()

    def review(self) -> None:
        if self.window is not None:
            self.window.resize(1000, 760)
            if self.screen_size is not None:
                screen_width, screen_height = self.screen_size
                self.window.move(
                    max(20, (screen_width - 1000) // 2),
                    max(20, (screen_height - 760) // 2),
                )

    def end_session(self) -> None:
        self.session.mark_stopped("Ended by user")
        self.shutdown_requested.set()
        if self.window is not None:
            self.window.destroy()

    def dismiss(self, *_arguments: object) -> None:
        if not self.shutdown_requested.is_set():
            self.session.mark_stopped("Window closed")
            self.shutdown_requested.set()


def show_corner_window(url: str, actions: WindowActions, force_browser: bool) -> bool:
    """Show a native window and return True, or open a browser fallback."""
    if force_browser:
        webbrowser.open(url)
        return False

    try:
        import webview
    except (ImportError, OSError):
        webbrowser.open(url)
        return False

    screen_size = primary_screen_size()
    window = webview.create_window(
        "AikiMap — agent session",
        url,
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        resizable=True,
        frameless=True,
        easy_drag=False,
        on_top=True,
        js_api=actions,
        background_color="#f6f1e7",
    )
    actions.attach_window(window, screen_size)

    def prepare_window(*_arguments: object) -> None:
        if screen_size is not None:
            window.move(*corner_position(*screen_size))
        window.evaluate_js(_CONTROL_SCRIPT)

    window.events.loaded += prepare_window
    window.events.closed += actions.dismiss
    try:
        webview.start()
    except Exception:
        webbrowser.open(url)
        return False
    return True
