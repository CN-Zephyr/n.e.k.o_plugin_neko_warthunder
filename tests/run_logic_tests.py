"""No-host entry point using the project's standard pytest environment.

Run with ``uv run python tests/run_logic_tests.py``. Extra pytest options such
as ``-k`` or ``--collect-only`` are forwarded. Fixtures, parametrization,
autouse isolation and teardown come from pytest and tests/conftest.py.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_PLUGIN_DIR = _TESTS_DIR.parent


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    # Keep pytest imports and test SDK stubs isolated from programmatic callers.
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-c", str(_TESTS_DIR / "pytest.ini"),
         str(_TESTS_DIR), "-q", *args],
        cwd=_PLUGIN_DIR,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
