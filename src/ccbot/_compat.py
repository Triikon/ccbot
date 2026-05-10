"""Runtime compatibility shims for libtmux on Windows + psmux.

ccbot uses libtmux, which targets real tmux. Three issues surface when the
underlying tmux is psmux (the Windows-native tmux clone). All three are
monkey-patched here at import time; removing this module entirely should be
possible once the corresponding fixes land in libtmux upstream.

1. **Encoding**: libtmux's ``tmux_cmd`` opens ``subprocess.Popen`` with
   ``text=True`` but no explicit ``encoding``. On Windows that defaults to
   ``cp1252``, which mangles psmux's UTF-8 output — particularly the
   ``U+241E`` format separator — and every subsequent parse silently fails.

2. **parse_output strictness**: libtmux's ``parse_output`` uses
   ``zip(..., strict=True)``. psmux can emit a leading separator before the
   first value, producing one extra empty entry; the strict zip then raises
   instead of just dropping the empty leading entry.

3. **Joined start-directory arg**: libtmux's ``Session.new_window`` passes
   ``-c<path>`` as a single argument (tmux accepts this form). psmux silently
   ignores it, so new windows land at the parent shell's cwd instead of the
   chosen project directory. We rewrite any ``-c<path>``-shaped argument
   passed to ``tmux_cmd`` into the split ``-c``, ``<path>`` form, which both
   real tmux and psmux accept.

The patches are idempotent and safe on Linux/macOS — they detect the joined
``-c`` form by path shape (absolute path) and only activate when present.
"""

from __future__ import annotations

import logging
import re
import subprocess as _real_subprocess

logger = logging.getLogger(__name__)

_applied = False


def _patch_subprocess_encoding() -> None:
    """Force ``encoding='utf-8'`` on libtmux's text-mode subprocess pipes."""
    import libtmux.common

    class _Popen(_real_subprocess.Popen):
        def __init__(self, *args, **kwargs):
            if kwargs.get("text") is True and "encoding" not in kwargs:
                kwargs["encoding"] = "utf-8"
            super().__init__(*args, **kwargs)

    class _SubprocessShim:
        Popen = _Popen
        PIPE = _real_subprocess.PIPE
        STDOUT = _real_subprocess.STDOUT
        DEVNULL = _real_subprocess.DEVNULL

        def __getattr__(self, name):  # delegate everything else
            return getattr(_real_subprocess, name)

    libtmux.common.subprocess = _SubprocessShim()


def _patch_parse_output() -> None:
    """Relax ``parse_output`` to handle psmux's leading separator quirk."""
    import libtmux.neo
    from libtmux.formats import FORMAT_SEPARATOR

    def parse_output(output: str):
        formats, _ = libtmux.neo.get_output_format()
        values = output.split(FORMAT_SEPARATOR)
        if values and values[-1] == "":
            values = values[:-1]
        # psmux can emit a leading separator before the first value; when
        # that happens, values is one over field count and the first entry
        # is empty.
        if len(values) == len(formats) + 1 and values[0] == "":
            values = values[1:]
        formatter = dict(zip(formats, values))
        return {k: v for k, v in formatter.items() if v}

    libtmux.neo.parse_output = parse_output


_JOINED_C_PATH = re.compile(r"^-c(?:[A-Za-z]:[\\/]|/|\\\\?)")


def _patch_tmux_cmd_args() -> None:
    """Rewrite ``-c<path>`` args into split ``-c``, ``<path>`` form for psmux."""
    import libtmux.common

    _original_init = libtmux.common.tmux_cmd.__init__

    def patched_init(self, *args, tmux_bin=None):
        new_args: list = []
        for arg in args:
            if isinstance(arg, str) and _JOINED_C_PATH.match(arg):
                new_args.append("-c")
                new_args.append(arg[2:])
            else:
                new_args.append(arg)
        return _original_init(self, *new_args, tmux_bin=tmux_bin)

    libtmux.common.tmux_cmd.__init__ = patched_init  # type: ignore[method-assign]


def apply() -> None:
    """Apply all libtmux compatibility patches. Safe to call multiple times."""
    global _applied
    if _applied:
        return
    try:
        _patch_subprocess_encoding()
        _patch_parse_output()
        _patch_tmux_cmd_args()
        _applied = True
        logger.debug("libtmux compatibility shims applied")
    except Exception:
        logger.exception("Failed to apply libtmux compatibility shims")
