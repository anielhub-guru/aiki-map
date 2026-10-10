"""Display AikiMap in a compact native webview with a browser fallback."""

from __future__ import annotations

import subprocess
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
  const controls = document.createElement('div');
  controls.id = 'aikimap-session-controls';
  controls.innerHTML = `
    <button id="aikimap-hide" type="button">Hide</button>
    <button id="aikimap-review" type="button">Review</button>
    <button id="aikimap-end" type="button">End session</button>
  `;
  Object.assign(controls.style, {
    position: 'fixed', top: '10px', right: '10px', zIndex: '2147483647',
    display: 'flex', gap: '6px', padding: '6px', borderRadius: '9px',
    background: 'rgba(25, 28, 38, 0.88)', boxShadow: '0 4px 18px rgba(0,0,0,.2)'
  });
  controls.querySelectorAll('button').forEach((button) => Object.assign(button.style, {
    border: '0', borderRadius: '6px', padding: '6px 9px', cursor: 'pointer',
    color: '#f5f2ea', background: '#4c4566', font: '12px system-ui'
  }));
  document.body.appendChild(controls);
  document.getElementById('aikimap-hide').onclick = () => window.pywebview.api.hide();
  document.getElementById('aikimap-review').onclick = () => window.pywebview.api.review();
  document.getElementById('aikimap-end').onclick = () => {
    if (window.confirm('End the wrapped agent session?')) window.pywebview.api.end_session();
  };
})();
"""


class WindowActions:
    """Methods exposed only to the local native AikiMap webview."""

    def __init__(self, process: subprocess.Popen[bytes], session: SessionState) -> None:
        self.process = process
        self.session = session
        self.window: Any = None

    def hide(self) -> None:
        if self.window is not None:
            self.window.minimize()

    def review(self) -> None:
        if self.window is not None:
            self.window.resize(1000, 760)

    def end_session(self) -> None:
        if self.process.poll() is None:
            self.session.mark_stopped("Ended by user")
            self.process.terminate()

    def dismiss(self, *_arguments: object) -> None:
        self.session.dismiss()


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
        on_top=True,
        js_api=actions,
        background_color="#f6f1e7",
    )
    actions.window = window

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
