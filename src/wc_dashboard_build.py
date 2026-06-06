"""Console-script launcher for ``wc-dashboard-build`` (the ``[project.scripts]`` target).

WHY THIS MODULE EXISTS
----------------------
``wcmodel`` is a src-layout package. It is importable under pytest via
``[tool.pytest.ini_options] pythonpath = ["src"]`` and, for the operator CLI, via
uv's editable install — a ``*.pth`` file that puts ``…/src`` onto ``sys.path``.

On this machine that editable ``*.pth`` does not survive: uv writes it under an
iCloud-synced ``~/Desktop`` checkout and it ends up carrying the macOS ``UF_HIDDEN``
file flag (you can see it as ``hidden`` in ``ls -lO``; iCloud also leaves ``… 2.pth``
conflict copies). CPython 3.12's ``site.addpackage`` *skips any ``.pth`` marked
hidden*, so ``…/src`` never reaches ``sys.path`` and the generated console-script
wrapper — ``from wcmodel.dashboard.cli import main`` — dies with
``ModuleNotFoundError: No module named 'wcmodel'`` (which is exactly the operator's
report). Re-running ``uv sync`` only re-opens the same race: the import works for a
few seconds until the flag is re-applied.

THE FIX
-------
This launcher is shipped as a *physical* top-level module in site-packages (via
hatchling ``force-include``), so it is importable regardless of the editable
``.pth`` state — site-packages is on ``sys.path`` via the venv itself, not via a
``.pth``. The launcher makes ``wcmodel`` importable, then delegates to the real CLI.

It deliberately does NOT duplicate or touch any betting logic or the dry-run gate:
all of that stays in ``wcmodel.dashboard.cli.main``, which this module simply calls.
The ``pythonpath = ["src"]`` pytest convention is untouched.
"""
from __future__ import annotations

import glob
import os
import sys


def _editable_src_roots(sitedirs: list[str] | None = None) -> list[str]:
    """Recover editable source roots from ``.pth`` files that ``site`` refused to process.

    A hidden ``.pth`` is still readable — ``site`` only declines to *process* it — so we
    read every ``.pth`` in the given site dirs and return any recorded directory that
    actually contains a ``wcmodel`` package. This is precisely the path ``site`` would
    have added had the file not been flagged hidden.
    """
    if sitedirs is None:
        sitedirs = [p for p in sys.path if p and os.path.isdir(p)]
    roots: list[str] = []
    for sitedir in sitedirs:
        for pth in glob.glob(os.path.join(sitedir, "*.pth")):
            try:
                with open(pth, "r", encoding="utf-8") as fh:
                    lines = fh.read().splitlines()
            except OSError:
                continue
            for line in lines:
                line = line.strip()
                if not line or line.startswith(("#", "import ", "import\t")):
                    continue  # comments and exec-lines are not path entries
                if os.path.isdir(os.path.join(line, "wcmodel")) and line not in roots:
                    roots.append(line)
    return roots


def _ensure_wcmodel_importable() -> None:
    """Make ``import wcmodel`` succeed for both editable and non-editable installs.

    Fast path: a non-editable install puts ``wcmodel`` physically in site-packages, so the
    import just works and we return immediately. Slow path (the hidden-``.pth`` case): we
    recover the editable src root(s) and prepend them to ``sys.path``.
    """
    try:
        import wcmodel  # noqa: F401  (probe only)
        return
    except ModuleNotFoundError:
        pass
    for root in _editable_src_roots():
        if root not in sys.path:
            sys.path.insert(0, root)


def main(argv: list[str] | None = None) -> int | None:
    """Entry point for the ``wc-dashboard-build`` console script.

    Ensures ``wcmodel`` is importable, then hands off to the real, fully-gated CLI in
    ``wcmodel.dashboard.cli`` (dry-run default; ``--no-dry-run`` refuses with ``SystemExit``).
    """
    _ensure_wcmodel_importable()
    from wcmodel.dashboard.cli import main as _cli_main
    return _cli_main(argv)


if __name__ == "__main__":          # pragma: no cover
    raise SystemExit(main())
