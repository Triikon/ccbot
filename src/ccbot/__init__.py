"""CCBot - Telegram Bot for managing Claude Code sessions via tmux.

Package entry point. Exports the version string only; all functional
modules are imported lazily by main.py to keep startup fast.
"""

__version__ = "0.1.0"

# Apply libtmux compatibility shims before any module imports libtmux.
# Idempotent; no-op on platforms where the underlying tmux already behaves.
from . import _compat as _compat  # noqa: F401, E402
_compat.apply()
