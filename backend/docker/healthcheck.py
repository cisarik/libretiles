#!/usr/bin/env python3
from __future__ import annotations

import os
import socket
import sys


def main() -> int:
    host = os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",", 1)[0].strip()
    if not host:
        return 1
    request = (
        f"GET /api/catalog/models/ HTTP/1.1\r\nHost: {host}\r\n"
        "X-Forwarded-For: 127.0.0.1\r\nX-Forwarded-Port: 443\r\n"
        "X-Forwarded-Proto: https\r\nConnection: close\r\n\r\n"
    ).encode("ascii")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(3)
            client.connect("/run/libretiles/backend.sock")
            client.sendall(request)
            status = client.recv(128).split(b"\r\n", 1)[0]
    except (OSError, UnicodeError):
        return 1
    return 0 if status.startswith(b"HTTP/1.1 200 ") else 1


if __name__ == "__main__":
    sys.exit(main())
