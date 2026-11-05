"""Small Win32 helpers (all safe no-ops off Windows)."""
import ctypes
import os

IS_WIN = os.name == "nt"
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT, WS_EX_LAYERED, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x20, 0x80000, 0x80, 0x08000000
HWND_TOPMOST, SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW = -1, 0x1, 0x2, 0x10, 0x40
WDA_NONE, WDA_EXCLUDEFROMCAPTURE = 0x0, 0x11


def window_rect(hwnd):
    """(left, top, right, bottom) of a window in real screen pixels, or None."""
    if not IS_WIN:
        return None
    try:
        from ctypes import wintypes
        r = wintypes.RECT()
        if ctypes.windll.user32.GetWindowRect(int(hwnd), ctypes.byref(r)):
            return r.left, r.top, r.right, r.bottom
    except Exception:
        pass
    return None


def set_topmost(hwnd):
    """Keep a window above everything else (without taking focus). Call periodically."""
    if IS_WIN:
        try:
            ctypes.windll.user32.SetWindowPos(int(hwnd), HWND_TOPMOST, 0, 0, 0, 0,
                                              SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
        except Exception:
            pass


def set_click_through(hwnd, on):
    """Let the mouse pass straight through the window (and never take keyboard focus)."""
    if not IS_WIN:
        return False
    try:
        u = ctypes.windll.user32
        style = u.GetWindowLongW(int(hwnd), GWL_EXSTYLE)
        style |= WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        style = (style | WS_EX_TRANSPARENT) if on else (style & ~WS_EX_TRANSPARENT)
        u.SetWindowLongW(int(hwnd), GWL_EXSTYLE, style)
        return True
    except Exception:
        return False


def set_capture_hidden(hwnd, hidden):
    """Hide (or show) a window in screenshots and screen recordings."""
    if IS_WIN:
        try:
            ctypes.windll.user32.SetWindowDisplayAffinity(int(hwnd), WDA_EXCLUDEFROMCAPTURE if hidden else WDA_NONE)
        except Exception:
            pass
