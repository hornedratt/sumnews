"""The FastAPI web layer: request dependencies, routes, and Jinja templates.

`create_app` lives in :mod:`sumnews.app`; this package holds what it mounts.
"""

from sumnews.web.routes import router

__all__ = ["router"]
