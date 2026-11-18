"""SSRF-safe outbound HTTP client used by HTTP nodes, integrations and AI tools."""

from __future__ import annotations

import ipaddress
import json
import socket
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from app.core.config import settings
from app.core.errors import ExternalServiceError, ValidationError

BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata",
    "metadata.google.internal",
}

ALLOWED_SCHEMES = {"http", "https"}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
MAX_REDIRECTS = 3


@dataclass
class HttpResponse:
    status_code: int
    headers: dict[str, str]
    body: Any
    text: str
    url: str
    elapsed_ms: float


@dataclass
class _Policy:
    allow_private: bool = False
    allowed_hosts: set[str] = field(default_factory=set)


def _is_forbidden_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(
        [
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_reserved,
            ip.is_unspecified,
        ]
    )


def validate_outbound_url(
    url: str,
    *,
    allow_private_networks: bool | None = None,
    allowed_hosts: set[str] | None = None,
) -> str:
    """Validate an outbound URL and resolve every address it points to.

    Rejects non-HTTP schemes, embedded credentials, blocked hostnames and, unless
    explicitly enabled, private/loopback/link-local/reserved IP destinations.
    """
    if allow_private_networks is None:
        allow_private_networks = settings.http_allow_private_networks

    url = (url or "").strip()
    if not url:
        raise ValidationError("A URL is required.")
    if len(url) > 2048:
        raise ValidationError("URL is too long.")

    parts = urlsplit(url)
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise ValidationError("Only http and https URLs are allowed.")
    if parts.username or parts.password:
        raise ValidationError("URLs with embedded credentials are not allowed.")
    hostname = parts.hostname
    if not hostname:
        raise ValidationError("URL must include a hostname.")

    normalized_host = hostname.rstrip(".").lower()

    if allowed_hosts:
        normalized_allow = {h.lower().strip() for h in allowed_hosts if h}
        if normalized_allow and normalized_host not in normalized_allow:
            raise ValidationError("Destination host is not allowed by policy.")

    if allow_private_networks:
        return urlunsplit(parts)

    if normalized_host in BLOCKED_HOSTNAMES:
        raise ValidationError("Destination host is not allowed.")

    if normalized_host.endswith(".localhost"):
        raise ValidationError("Destination host is not allowed.")

    try:
        literal_ip = ipaddress.ip_address(normalized_host.strip("[]"))
        if _is_forbidden_ip(literal_ip):
            raise ValidationError("Destination address is not allowed.")
        return urlunsplit(parts)
    except ValueError:
        pass

    try:
        port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise ValidationError("URL contains an invalid port.") from exc

    try:
        resolved = socket.getaddrinfo(normalized_host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ExternalServiceError(f"Could not resolve host '{normalized_host}'.") from exc

    if not resolved:
        raise ExternalServiceError(f"Could not resolve host '{normalized_host}'.")

    for family_info in resolved:
        address = family_info[4][0]
        try:
            candidate = ipaddress.ip_address(address)
        except ValueError:
            continue
        if _is_forbidden_ip(candidate):
            raise ValidationError("Destination address is not allowed.")

    return urlunsplit(parts)


def _headers_to_dict(headers: httpx.Headers) -> dict[str, str]:
    return {key: value for key, value in headers.items()}


def _decode_body(content: bytes, content_type: str) -> Any:
    text = content.decode("utf-8", errors="replace")
    if "application/json" in content_type.lower():
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return text


async def safe_http_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json_body: Any = None,
    data: Any = None,
    content: bytes | str | None = None,
    timeout_seconds: float | None = None,
    max_response_bytes: int | None = None,
    allow_private_networks: bool | None = None,
    allowed_hosts: set[str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> HttpResponse:
    """Perform an outbound HTTP request with SSRF protection and size limits."""
    timeout = timeout_seconds or settings.http_timeout_seconds
    limit = max_response_bytes or settings.http_max_response_bytes
    current_url = validate_outbound_url(
        url,
        allow_private_networks=allow_private_networks,
        allowed_hosts=allowed_hosts,
    )

    request_headers = dict(headers or {})
    request_headers.setdefault("User-Agent", "NexusAI/1.0 (+https://github.com/Igor538/nexus-ai)")
    request_headers.setdefault("Accept", "application/json, text/plain, */*")

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        transport=transport,
    ) as client:
        import time

        started = time.perf_counter()
        response = await client.request(
            method.upper(),
            current_url,
            headers=request_headers,
            params=params,
            json=json_body,
            data=data,
            content=content,
        )
        redirects = 0
        while response.status_code in REDIRECT_STATUSES and "location" in response.headers:
            redirects += 1
            if redirects > MAX_REDIRECTS:
                raise ExternalServiceError("Too many redirects.")
            current_url = validate_outbound_url(
                urljoin(str(response.url), response.headers["location"]),
                allow_private_networks=allow_private_networks,
                allowed_hosts=allowed_hosts,
            )
            if response.status_code == 303 or (
                response.status_code in {301, 302} and method.upper() == "POST"
            ):
                response = await client.request("GET", current_url, headers=request_headers)
            else:
                response = await client.request(
                    method.upper(),
                    current_url,
                    headers=request_headers,
                    params=params,
                    json=json_body,
                    data=data,
                    content=content,
                )

        content_bytes = response.content
        truncated = len(content_bytes) > limit
        if truncated:
            content_bytes = content_bytes[:limit]

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        content_type = response.headers.get("content-type", "")
        return HttpResponse(
            status_code=response.status_code,
            headers=_headers_to_dict(response.headers),
            body=_decode_body(content_bytes, content_type),
            text=content_bytes.decode("utf-8", errors="replace"),
            url=str(response.url),
            elapsed_ms=elapsed_ms,
        )
