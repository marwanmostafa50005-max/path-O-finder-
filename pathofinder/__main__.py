"""Entry point: `python -m pathofinder` and the PyInstaller-frozen exe.

ABSOLUTE import only: PyInstaller executes this file as a top-level script
with no package context, so a relative import ("from .app import ...")
raises "attempted relative import with no known parent package" in the
shipped binary while working fine from source. Guarded by an invariant test.
"""

from pathofinder.app import main

if __name__ == "__main__":
    raise SystemExit(main())
