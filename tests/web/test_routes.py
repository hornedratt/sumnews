"""Route inventory guard.

`create_app()` runs no lifespan, so this is a pure structural check: every route we define must
be listed below with its access class. v1 is an internal unauthenticated tool, so the only class
is PUBLIC — but a new route still has to be added here deliberately, which is the point.
"""

from starlette.routing import Mount
from sumnews.app import create_app
from sumnews.web.routes import router

# (method, path) -> access class. Adding a route without listing it here fails the test.
ROUTE_ACCESS = {
    ("GET", "/"): "PUBLIC",
    ("GET", "/items/{item_id}"): "PUBLIC",
    ("POST", "/items/{item_id}"): "PUBLIC",
    ("POST", "/ingest/run"): "PUBLIC",
    ("GET", "/healthz"): "PUBLIC",
}


def _declared_routes() -> set[tuple[str, str]]:
    declared: set[tuple[str, str]] = set()
    for route in router.routes:
        for method in getattr(route, "methods", None) or ():
            if method in ("HEAD", "OPTIONS"):
                continue
            declared.add((method, route.path))
    return declared


def test_every_route_is_classified() -> None:
    assert _declared_routes() == set(ROUTE_ACCESS)


def test_static_is_mounted() -> None:
    app = create_app()
    assert any(isinstance(route, Mount) and route.path == "/static" for route in app.routes)
