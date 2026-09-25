"""Top-level package shim for legacy imports.

The test suite (and other modules) import the FastAPI application using
``import app`` as if the package were located at the repository root.  In the
actual project layout the code lives under ``backend_fastapi/app``.  To avoid
touching every import statement we expose a lightweight package that forwards
submodule resolution to the real location.

By populating ``__path__`` with the absolute path to ``backend_fastapi/app`` we
turn this directory into a namespace package that transparently resolves
``app.core.*``, ``app.shared.*`` etc.  No additional code is executed and the
behaviour is identical to having the package at the top level.
"""

import os
# Ensure that core third‑party packages are importable before any submodule
# resolution occurs. Importing ``pydantic`` here forces Python to load the
# package from the virtual‑env site‑packages early, avoiding a rare import‑time
# ``ModuleNotFoundError``` that was observed when the test suite loads the shim.
# The import is deliberately unused – it merely guarantees the module is in
# ``sys.modules`` for subsequent imports.
import pydantic  # noqa: F401

# Resolve the path to the actual ``backend_fastapi/app`` directory relative to
# this shim's location.
_real_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "backend_fastapi", "app")
)

# ``__path__`` tells the import machinery where to look for submodules.  We
# extend the existing path (which normally contains the directory of this shim
# itself) with the real package location.  Keeping the original entry ensures
# that imports that rely on the standard package layout – including third‑party
# libraries – continue to resolve correctly.
__path__ = list(__path__) + [_real_path]

# The shim deliberately does not import any of the submodules eagerly.  They
# will be loaded on demand the first time they are accessed via the standard
# ``import app.<submodule>`` syntax.
