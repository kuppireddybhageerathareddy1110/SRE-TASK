"""
kvserver.py
-----------
Stage 1. A dumb in-memory key-value map behind a TCP listener. Thread per
connection. Knows nothing about proxies, replication, or any other copy of
itself -- all of that intelligence lives in proxy.py.

Client-facing commands:
    SET <key> <value>   -> OK
    GET <key>            -> VALUE <value> | NOT_FOUND
    DEL <key>            -> OK | NOT_FOUND
    PING                  -> PONG
    (anything else)       -> ERR bad_command   (connection stays open)

Admin commands (used by proxy.py, and directly for Stage 4/5 testing):
    INFO                  -> INFO <uptime_seconds> <key_count>
    DUMP                  -> DUMP <json of the whole map>
    LOAD <key> <value>   -> LOADED | SKIPPED   (set-if-absent)
    CORRUPT <key> <value> -> OK                (same effect as SET; a
                             separate verb purely so Stage 5 tests can
                             manufacture disagreement deliberately)
"""

from __future__ import annotations
import argparse
import json
import socket
import threading
import time

from protocol import LineConn, ConnectionClosed


class KVServer:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._lock = threading.RLock()
        self._start_time = time.monotonic()

    def get(self, key: str) -> str | None:
        with self._lock:
            return self._data.get(key)

    def set(self, key: str, value: str) -> None:
        with self._lock:
            self._data[key] = value

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._data.pop(key, None) is not None

    def set_if_absent(self, key: str, value: str) -> bool:
        """Used by LOAD. Returns True if it actually set the key (it was
        absent), False if a value was already present (skipped)."""
        with self._lock:
            if key in self._data:
                return False
            self._data[key] = value
            return True

    def dump(self) -> dict[str, str]:
        with self._lock:
            return dict(self._data)

    def key_count(self) -> int:
        with self._lock:
            return len(self._data)

    def uptime(self) -> float:
        return time.monotonic() - self._start_time

    def dispatch(self, line: str) -> str:
        if not line.strip():
            return "ERR bad_command"
        parts = line.split(" ", 2)
        verb = parts[0].upper()

        if verb == "SET" and len(parts) == 3:
            self.set(parts[1], parts[2])
            return "OK"

        if verb == "GET" and len(parts) == 2:
            value = self.get(parts[1])
            return f"VALUE {value}" if value is not None else "NOT_FOUND"

        if verb == "DEL" and len(parts) == 2:
            return "OK" if self.delete(parts[1]) else "NOT_FOUND"

        if verb == "PING" and len(parts) == 1:
            return "PONG"

        if verb == "INFO" and len(parts) == 1:
            return f"INFO {self.uptime():.3f} {self.key_count()}"

        if verb == "DUMP" and len(parts) == 1:
            return "DUMP " + json.dumps(self.dump())

        if verb == "LOAD" and len(parts) == 3:
            return "LOADED" if self.set_if_absent(parts[1], parts[2]) else "SKIPPED"

        if verb == "CORRUPT" and len(parts) == 3:
            self.set(parts[1], parts[2])
            return "OK"

        return "ERR bad_command"


def _handle_conn(sock: socket.socket, store: KVServer) -> None:
    conn = LineConn(sock)
    try:
        while True:
            line = conn.read_line()
            reply = store.dispatch(line)
            conn.send_line(reply)
    except ConnectionClosed:
        pass
    finally:
        conn.close()


def serve(host: str, port: int) -> None:
    store = KVServer()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((host, port))
    listener.listen(128)
    print(f"[kvserver] listening on {host}:{port}", flush=True)
    try:
        while True:
            sock, _addr = listener.accept()
            t = threading.Thread(target=_handle_conn, args=(sock, store), daemon=True)
            t.start()
    except KeyboardInterrupt:
        pass
    finally:
        listener.close()


def main() -> None:
    p = argparse.ArgumentParser(description="In-memory KV server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, required=True)
    args = p.parse_args()
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
