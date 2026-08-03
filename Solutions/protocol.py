"""
protocol.py
-----------
Turns a raw TCP socket into "read one line, send one line". TCP is a byte
stream, not a message stream, so a single recv() can return half a command,
one whole command, or several -- this class buffers bytes per-connection
and only hands back a line once a full '\n' has arrived.

Used identically by every TCP link in the system: client<->kvserver,
client<->proxy, and proxy<->backend.
"""

from __future__ import annotations
import socket


class ConnectionClosed(Exception):
    """Raised when the peer closed the socket (a recv() of b"" -- TCP's
    zero-byte-read EOF signal) instead of sending a line. Kept distinct
    from an empty string so callers can't mistake "peer hung up" for
    "peer sent a blank line"."""


class LineConn:
    def __init__(self, sock: socket.socket):
        self.sock = sock
        self._buf = b""

    def read_line(self) -> str:
        while b"\n" not in self._buf:
            chunk = self.sock.recv(4096)
            if chunk == b"":
                raise ConnectionClosed()
            self._buf += chunk
        line, _, rest = self._buf.partition(b"\n")
        self._buf = rest
        return line.decode("utf-8", errors="replace")

    def send_line(self, line: str) -> None:
        self.sock.sendall(line.encode("utf-8") + b"\n")

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass
