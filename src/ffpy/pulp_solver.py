"""Ensure lineup optimization has a working PuLP solver on this machine.

``LineupOptimizer`` uses ``pulp.PULP_CBC_CMD``. PuLP 4 removed that symbol;
PuLP 3 still ships an x86_64 CBC binary that fails on Apple Silicon
(``Bad CPU type``). When the bundled CBC cannot run, swap ``PULP_CBC_CMD``
for HiGHS (``highspy`` via ``pulp[highs]``).
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

_CONFIGURED = False
_BACKEND = "unset"


def _bundled_cbc_path() -> str | None:
    try:
        from pulp.apis import coin_api
    except ImportError:
        return None
    path = getattr(coin_api, "pulp_cbc_path", None)
    if not path:
        return None
    return str(path)


def _cbc_binary_runs(path: str) -> bool:
    if not path or not os.path.isfile(path):
        return False
    if not os.access(path, os.X_OK):
        return False
    try:
        completed = subprocess.run(
            [path],
            input="quit\n",
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except OSError:
        # Errno 86 Bad CPU type (x86 CBC on arm64 without Rosetta), missing loader, etc.
        return False
    except subprocess.TimeoutExpired:
        return False
    # SIGKILL / crash (seen with some cbcbox builds) → unusable.
    if completed.returncode < 0:
        return False
    return True


def _install_highs_as_pulp_cbc() -> str:
    import pulp
    import pulp.apis.coin_api as coin_api
    from pulp import HiGHS

    class _HighsAsPulpCbc(HiGHS):
        """Stand-in for ``PULP_CBC_CMD`` so callers keep working without CBC."""

        def __init__(self, msg: bool = True, **_kwargs: Any) -> None:
            super().__init__(msg=msg)

    pulp.PULP_CBC_CMD = _HighsAsPulpCbc  # type: ignore[attr-defined, assignment]
    coin_api.PULP_CBC_CMD = _HighsAsPulpCbc  # type: ignore[assignment]
    return "highs"


def ensure_lineup_solver(*, force: bool = False) -> str:
    """Configure a usable ``PULP_CBC_CMD`` and return the active backend name.

    Returns ``cbc`` when the bundled binary works, ``highs`` after a fallback
    shim, or ``missing`` if neither is available.
    """

    global _CONFIGURED, _BACKEND
    if _CONFIGURED and not force:
        return _BACKEND

    try:
        from pulp import PULP_CBC_CMD  # noqa: F401
    except ImportError:
        _BACKEND = "missing"
        _CONFIGURED = True
        logger.error("PuLP is not installed — lineup optimize will fail")
        return _BACKEND

    cbc_path = _bundled_cbc_path()
    if cbc_path and _cbc_binary_runs(cbc_path):
        _BACKEND = "cbc"
        _CONFIGURED = True
        logger.info(
            "Lineup solver: bundled CBC (%s %s)",
            platform.system(),
            platform.machine(),
        )
        return _BACKEND

    try:
        _BACKEND = _install_highs_as_pulp_cbc()
        _CONFIGURED = True
        logger.warning(
            "Bundled PuLP CBC unusable on %s/%s — using HiGHS for lineup optimize",
            platform.system(),
            platform.machine(),
        )
        return _BACKEND
    except ImportError:
        _BACKEND = "missing"
        _CONFIGURED = True
        logger.error(
            "Bundled PuLP CBC unusable and highspy missing — install pulp[highs]"
        )
        return _BACKEND


def active_lineup_solver() -> str:
    return _BACKEND


__all__ = ["active_lineup_solver", "ensure_lineup_solver"]
