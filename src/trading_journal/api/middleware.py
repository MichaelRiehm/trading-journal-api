"""Request ids, one access log line per request, and the last-resort 500 (ADR 0014).

A plain ASGI middleware rather than Starlette's BaseHTTPMiddleware: it wraps the whole
request in one task, so the request context is set for everything inside it, and it
doesn't buffer or re-wrap the response.
"""

import logging
import re
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from trading_journal.api.errors import problem_response
from trading_journal.logging_config import RequestContext, request_context

logger = logging.getLogger("trading_journal.request")

REQUEST_ID_HEADER = "X-Request-ID"
# Accepted from the client only if it can't inject anything into logs or headers.
_SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER, "")
        request_id = incoming if _SAFE_REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
        token = request_context.set(RequestContext(request_id=request_id))
        status = 500
        response_started = False
        started_at = time.perf_counter()

        async def send_with_id(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status = message["status"]
                MutableHeaders(scope=message).append(REQUEST_ID_HEADER, request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            # Logged once, here, with the traceback; the client gets no internals.
            logger.exception("Unhandled error")
            if response_started:
                raise  # too late to send a 500; let the server close the connection
            response = problem_response(500, "Internal server error", instance=scope["path"])
            await response(scope, receive, send_with_id)
        finally:
            logger.info(
                "request",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],  # never the query string
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started_at) * 1000, 1),
                },
            )
            request_context.reset(token)
