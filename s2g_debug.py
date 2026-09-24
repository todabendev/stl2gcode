# s2g_debug.py: 2026-05-26 - 1706b
# Debug logging for CNC Router CAM Pipeline.
# Provides a shared counter and log() function.

import functools

s2g_debug_stamp = "s2g_debug.py: 2026-05-26 - 1706b"

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

_counter = 0
_debug = 0


def set_debug(lvl):
    global _debug
    _debug = lvl


def debug_enabled(test = 0):
    return _debug > test


def reset():
    global _counter
    _counter = 0

# ---------------------------------------------------------------------------
# Core log function
# ---------------------------------------------------------------------------


def log(string, is_start):
    if not debug_enabled():
        return
    global _counter
    if _counter < 1:
        print(s2g_debug_stamp)
    if is_start:
        _counter += 1
        prefix = f"{_counter:5d}"
    else:
        prefix = f"{'':5s}"
    print(f"{prefix}\t{string}")

# ---------------------------------------------------------------------------
# Field formatting helpers
# ---------------------------------------------------------------------------

def ff(v):
    return f"{v:8.3f}"


def fi(v, w=4):
    return f"{v:{w}d}"


def flist(lst, w=4):
    return "[" + ",".join(f"{v:{w}d}" for v in lst) + "]"


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------

def trace(label=None):
    """
    Decorator factory: prints entry/exit with optional label.
    Usage: @dbg.trace("method label")
    No-op when debug is not enabled.
    """
    def decorator(method):
        @functools.wraps(method)
        def wrapper(self, *args, **kwargs):
            name = label if label else method.__name__
            if debug_enabled():
                log(f">>> {name}", True)
            try:
                result = method(self, *args, **kwargs)
            finally:
                if debug_enabled():
                    log(f"<<< {name}", False)
            return result
        return wrapper
    return decorator
