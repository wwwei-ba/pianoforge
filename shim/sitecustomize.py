"""Workspace shim: tempfile.mkdtemp on this host creates directories whose DACL
denies access to the sandboxed process (mode 0o700 is enforced as a restrictive ACL).
Re-implement mkdtemp with plain os.mkdir (mode 0o777) so pip and libraries work.
"""
import os as _os
import random as _random
import string as _string
import tempfile as _tempfile

_real_mkdtemp = _tempfile.mkdtemp
_ALPHABET = _string.ascii_lowercase + _string.digits


def _mkdtemp(suffix=None, prefix=None, dir=None):
    suffix = suffix or ""
    prefix = prefix or "tmp"
    dir = dir or _tempfile.gettempdir()
    for _ in range(1000):
        name = _os.path.join(dir, prefix + "".join(_random.choices(_ALPHABET, k=8)) + suffix)
        try:
            _os.mkdir(name, 0o777)
        except FileExistsError:
            continue
        return _os.path.abspath(name)
    raise FileExistsError("could not create a unique temporary directory")


_mkdtemp._shimmed = True  # type: ignore[attr-defined]
_tempfile.mkdtemp = _mkdtemp

# TemporaryDirectory holds a module-level reference to mkdtemp; refresh it.
if hasattr(_tempfile, "TemporaryDirectory"):
    _tempfile.TemporaryDirectory._mkdtemp = staticmethod(_mkdtemp)  # type: ignore[attr-defined]