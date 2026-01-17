"""Application middleware."""

import logging
import time
from contextvars import ContextVar
from typing import ClassVar
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Context variables for request-scoped data
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_ctx: ContextVar[str | None] = ContextVar("user_id", default=None)

logger = logging.getLogger(__name__)


def get_logging_context() -> dict[str, str | None]:
    """Get the current logging context.

    Returns a dict with request_id and user_id from context variables.
    Useful for adding context to log records.
    """
    return {
        "request_id": request_id_ctx.get(),
        "user_id": user_id_ctx.get(),
    }


def set_user_id(user_id: str | None) -> None:
    """Set the user_id in the logging context."""
    user_id_ctx.set(user_id)


class LoggingContextMiddleware(BaseHTTPMiddleware):
    """Middleware that adds logging context and timing to requests.

    Sets up context variables for request_id and logs request start/completion
    with timing information. Useful for request correlation in logs.

    The request_id is taken from X-Request-ID header if present,
    otherwise a new UUID is generated.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with logging context."""
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        request_id_ctx.set(request_id)

        start_time = time.perf_counter()

        logger.info(
            "Request started",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
            },
        )

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "Request completed",
            extra={
                "request_id": request_id,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )

        response.headers["X-Request-ID"] = request_id
        return response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware that adds a unique request ID to each request.

    The request ID is taken from the X-Request-ID header if present,
    otherwise a new UUID is generated. The ID is added to the response
    headers and is available in request.state.request_id.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """Add request ID to request state and response headers."""
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware that adds security headers to all responses.

    This includes:
    - Content-Security-Policy (CSP)
    - X-Content-Type-Options
    - X-Frame-Options
    - X-XSS-Protection
    - Referrer-Policy
    - Permissions-Policy

    Usage:
        app.add_middleware(SecurityHeadersMiddleware)

        # Or with custom CSP:
        app.add_middleware(
            SecurityHeadersMiddleware,
            csp_directives={
                "default-src": "'self'",
                "script-src": "'self' 'unsafe-inline'",
            }
        )
    """

    DEFAULT_CSP_DIRECTIVES: ClassVar[dict[str, str]] = {
        "default-src": "'self'",
        "script-src": "'self'",
        "style-src": "'self' 'unsafe-inline'",  # Allow inline styles for some UI libs
        "img-src": "'self' data: https:",
        "font-src": "'self' data:",
        "connect-src": "'self'",
        "frame-ancestors": "'none'",
        "base-uri": "'self'",
        "form-action": "'self'",
    }

    def __init__(
        self,
        app,
        csp_directives: dict | None = None,
        exclude_paths: set | None = None,
    ):
        super().__init__(app)
        self.csp_directives = csp_directives or self.DEFAULT_CSP_DIRECTIVES
        self.exclude_paths = exclude_paths or {"/docs", "/redoc", "/openapi.json"}

    async def dispatch(self, request: Request, call_next) -> Response:
        """Add security headers to the response."""
        response = await call_next(request)

        # Skip for docs/openapi endpoints which need different CSP
        if request.url.path in self.exclude_paths:
            return response

        # Build CSP header
        csp_value = "; ".join(
            f"{directive} {value}" for directive, value in self.csp_directives.items()
        )

        # Add security headers
        response.headers["Content-Security-Policy"] = csp_value
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(), payment=(), usb=()"
        )

        return response
