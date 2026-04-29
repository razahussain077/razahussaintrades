"""
pytest config — adds the backend `app` package to sys.path so tests can import
`from app...` without needing to install the package.
"""
import os
import sys

# backend/tests/ -> backend/ on sys.path so `import app...` works from tests.
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
