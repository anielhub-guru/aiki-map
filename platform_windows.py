"""Small cross-platform helpers for positioning the ambient window."""

from __future__ import annotations

import platform


WINDOW_WIDTH = 420
WINDOW_HEIGHT = 620
WINDOW_MARGIN = 20


def corner_position(
    screen_width: int,
    screen_height: int,
    window_width: int = WINDOW_WIDTH,
    window_height: int = WINDOW_HEIGHT,
    margin: int = WINDOW_MARGIN,
) -> tuple[int, int]:
    """Return a visible lower-right position for a primary display."""
    return (
        max(margin, screen_width - window_width - margin),
        max(margin, screen_height - window_height - margin),
    )


def primary_screen_size() -> tuple[int, int] | None:
    """Read primary display dimensions, returning None in headless sessions."""
    system = platform.system()
    if system == "Darwin":
        try:
            from AppKit import NSScreen

            size = NSScreen.mainScreen().frame().size
            return (int(size.width), int(size.height))
        except (AttributeError, ImportError, TypeError):
            return None

    if system == "Windows":
        try:
            import ctypes

            return (
                ctypes.windll.user32.GetSystemMetrics(0),
                ctypes.windll.user32.GetSystemMetrics(1),
            )
        except (AttributeError, OSError):
            return None

    try:
        import tkinter
    except ImportError:
        return None

    try:
        root = tkinter.Tk()
        root.withdraw()
        size = (root.winfo_screenwidth(), root.winfo_screenheight())
        root.destroy()
        return size
    except tkinter.TclError:
        return None
