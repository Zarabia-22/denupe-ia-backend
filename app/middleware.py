"""Protecciones HTTP ligeras para el servicio de IA.

El limitador es local al proceso: para varias instancias debe sustituirse por Redis
o por un limitador gestionado en el gateway/edge.
"""
from collections import defaultdict, deque
import logging
from time import monotonic
from uuid import uuid4
import os


logger = logging.getLogger("denupe.request_protection")


class _PayloadTooLarge(Exception):
    pass


def _positive_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{name} debe ser un entero") from exc
    if value < minimum:
        raise RuntimeError(f"{name} debe ser >= {minimum}")
    return value


class RequestProtectionMiddleware:
    def __init__(self, app):
        self.app = app
        self.max_body = _positive_int("MAX_REQUEST_BODY_BYTES", 16384)
        self.rate_limit = _positive_int("RATE_LIMIT_PER_MINUTE", 120)
        self._requests = defaultdict(deque)
        self._last_cleanup = monotonic()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid4())
        client = scope.get("client")
        client_ip = client[0] if client else "unknown"
        now = monotonic()
        if now - self._last_cleanup >= 60:
            stale_ips = [
                ip for ip, requests in self._requests.items()
                if not requests or now - requests[-1] >= 60
            ]
            for ip in stale_ips:
                self._requests.pop(ip, None)
            self._last_cleanup = now
        bucket = self._requests[client_ip]
        while bucket and now - bucket[0] >= 60:
            bucket.popleft()

        async def respond(status: int, payload: bytes, extra_headers=None):
            headers = [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(payload)).encode("ascii")),
                (b"x-request-id", request_id.encode("ascii")),
                (b"x-content-type-options", b"nosniff"),
                (b"referrer-policy", b"no-referrer"),
                (b"cache-control", b"no-store"),
            ]
            headers.extend(extra_headers or [])
            await send({"type": "http.response.start", "status": status, "headers": headers})
            await send({"type": "http.response.body", "body": payload})

        if len(bucket) >= self.rate_limit:
            await respond(429, b'{"detail":"Demasiadas solicitudes. Intenta nuevamente en un minuto."}', [(b"retry-after", b"60")])
            return

        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                declared = int(content_length)
            except ValueError:
                await respond(400, b'{"detail":"Content-Length invalido."}')
                return
            if declared < 0 or declared > self.max_body:
                await respond(413, b'{"detail":"El cuerpo de la solicitud supera el limite permitido."}')
                return

        bucket.append(now)
        received = 0
        response_started = False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body:
                    raise _PayloadTooLarge()
            return message

        async def protected_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                existing = list(message.get("headers", []))
                existing.extend([
                    (b"x-request-id", request_id.encode("ascii")),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"cache-control", b"no-store"),
                ])
                message = {**message, "headers": existing}
            await send(message)

        try:
            await self.app(scope, limited_receive, protected_send)
        except _PayloadTooLarge:
            if response_started:
                raise
            await respond(413, b'{"detail":"El cuerpo de la solicitud supera el limite permitido."}')
        except Exception as exc:
            if response_started:
                raise
            logger.error("Error interno request_id=%s tipo=%s", request_id, type(exc).__name__)
            await respond(500, b'{"detail":"Error interno. Usa el identificador de solicitud para reportarlo."}')
