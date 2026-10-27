from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.config import settings
from app.middleware.hsts import HSTSMiddleware


def test_hsts_header_absent_by_default(client):
    assert settings.enable_hsts is False
    resp = client.get("/health")
    assert "strict-transport-security" not in {k.lower() for k in resp.headers.keys()}


def test_hsts_middleware_sets_header_when_added():
    async def _ok(request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/", _ok)], middleware=[])
    app.add_middleware(HSTSMiddleware)

    with TestClient(app) as c:
        resp = c.get("/")
        assert resp.headers["strict-transport-security"] == "max-age=63072000; includeSubDomains"
