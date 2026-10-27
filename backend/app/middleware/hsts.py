from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class HSTSMiddleware(BaseHTTPMiddleware):
    """Only added to the app when settings.enable_hsts is true — see
    app/main.py and docs/deployment-runbook.md's TLS stance. This app never
    terminates TLS itself (a reverse proxy/load balancer does); this header only
    tells browsers to keep using HTTPS for future requests once that's in place."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response
