# Copyright (c) 2026 jlee-ax
"""Private loopback HTTP clients that cannot forward credentials to proxies."""

import socket

import httpx2


def create_client(url: str, token: str) -> httpx2.AsyncClient:
    """Use bounded requests and prohibit authenticated redirect following."""
    transport = httpx2.AsyncHTTPTransport(
        http2=True,
        retries=3,
        trust_env=False,
        limits=httpx2.Limits(
            max_connections=200,
            max_keepalive_connections=40,
            keepalive_expiry=30,
        ),
        socket_options=[(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)],
    )
    return httpx2.AsyncClient(
        transport=transport,
        base_url=url,
        headers={"Authorization": f"token {token}"},
        timeout=httpx2.Timeout(connect=5, read=30, write=10, pool=10),
        trust_env=False,
        follow_redirects=False,
    )
