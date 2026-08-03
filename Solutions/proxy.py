"""
proxy.py
--------
Stages 2-5 and the bonus. The only file that knows more than one backend
exists; every kvserver.py stays completely dumb.

  --backends host:port                    -> Stage 2 (one backend, transparent
                                              pass-through, fast-fail on death)
  --backends h1:p1,h2:p2,h3:p3             -> Stage 3 (broadcast writes,
                                              round-robin reads, need >=2 up
                                              to accept a write)
  (automatic, on whenever 2+ backends)     -> Stage 4 (a backend that comes
                                              back up is caught up from the
                                              longest-running survivor before
                                              it rejoins the read rotation)
  --majority-read                          -> Stage 5 (GET votes across every
                                              ready backend, repairs the
                                              minority)
  --quorum-write                           -> Bonus (a write is acknowledged
                                              once a majority of the backends
                                              it was sent to confirm)
  --no-catchup                             -> disables Stage 4

Proxy-only replies a lone kvserver.py never gives:
  ERR backend_unavailable   nothing reachable to answer this at all
  ERR write_unavailable     reachable, but fewer than 2 backends up (Stage 3)
  ERR no_majority           Stage 5: every ready backend disagreed
  INFO backends=<n> up=<n> read_ready=<n> read_mode=<roundrobin|majority>
"""

from __future__ import annotations
import argparse
import json
import socket
import threading
import time

from protocol import LineConn, ConnectionClosed


class Backend:
    """One persistent link to one kvserver.py, plus what the proxy currently
    believes about it. `up` and `read_ready` are deliberately separate --
    a backend spends real time with up=True, read_ready=False (mid catch-up)."""

    def __init__(self, host: str, port: int, name: str):
        self.host = host
        self.port = port
        self.name = name
        self.conn: LineConn | None = None
        self.lock = threading.Lock()
        self.up = False
        self.read_ready = False
        self.catching_up = False
        self.ever_checked = False

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"

    def _ensure_connected(self, timeout: float) -> None:
        if self.conn is not None:
            return
        sock = socket.create_connection((self.host, self.port), timeout=timeout)
        sock.settimeout(timeout)
        self.conn = LineConn(sock)

    def call(self, line: str, timeout: float) -> str | None:
        """One request/response round trip. Returns None (and drops the
        connection so the next call reconnects) on any failure -- caller
        decides what that means for `up`/`read_ready`."""
        with self.lock:
            try:
                self._ensure_connected(timeout)
                self.conn.sock.settimeout(timeout)
                self.conn.send_line(line)
                return self.conn.read_line()
            except (OSError, ConnectionClosed):
                if self.conn is not None:
                    self.conn.close()
                self.conn = None
                return None


def parse_backends(spec: str) -> list[Backend]:
    backends = []
    for i, item in enumerate(spec.split(",")):
        host, port = item.strip().split(":")
        backends.append(Backend(host, int(port), name=f"kv-{i + 1}"))
    return backends


class Proxy:
    def __init__(self, backends: list[Backend], op_timeout: float,
                 health_interval: float, health_timeout: float,
                 majority_read: bool, quorum_write: bool, catchup: bool):
        self.backends = backends
        self.op_timeout = op_timeout
        self.health_interval = health_interval
        self.health_timeout = health_timeout
        self.majority_read = majority_read
        self.quorum_write = quorum_write
        self.catchup = catchup
        self._rr_index = 0
        self._rr_lock = threading.Lock()

    # ---------------------------------------------------------- helpers --
    def _up(self) -> list[Backend]:
        return [b for b in self.backends if b.up]

    def _ready(self) -> list[Backend]:
        return [b for b in self.backends if b.read_ready]

    def _rr_pick(self, candidates: list[Backend]) -> Backend:
        with self._rr_lock:
            idx = self._rr_index % len(candidates)
            self._rr_index += 1
        return candidates[idx]

    def log(self, msg: str) -> None:
        print(f"[proxy] {msg}", flush=True)

    # -------------------------------------------------------- write path --
    def _do_write(self, verb: str, key: str, value: str | None) -> str:
        multi = len(self.backends) >= 2
        up = self._up()

        if multi:
            if len(up) < 2:
                return "ERR write_unavailable"
            targets = up
        else:
            if len(up) < 1:
                return "ERR backend_unavailable"
            targets = up

        line = f"{verb} {key} {value}" if value is not None else f"{verb} {key}"
        results: dict[str, str | None] = {}
        results_lock = threading.Lock()
        done = threading.Event()

        def call_one(b: Backend) -> None:
            reply = b.call(line, self.op_timeout)
            if reply is None:
                b.up = False
                b.read_ready = False
                self.log(f"backend {b.name} appears DOWN")
            with results_lock:
                results[b.name] = reply
                needed = (len(targets) // 2 + 1) if self.quorum_write else len(targets)
                ok_count = sum(1 for v in results.values() if v is not None)
                if ok_count >= needed:
                    done.set()

        threads = [threading.Thread(target=call_one, args=(b,), daemon=True) for b in targets]
        for t in threads:
            t.start()

        if self.quorum_write and len(targets) >= 2:
            needed = len(targets) // 2 + 1
            done.wait(timeout=self.op_timeout + 0.5)
            with results_lock:
                ok_count = sum(1 for v in results.values() if v is not None)
            if ok_count >= needed:
                return "OK"
            # fall through: not enough acks yet, wait for the rest
            for t in threads:
                t.join(timeout=self.op_timeout + 0.5)
            with results_lock:
                ok_count = sum(1 for v in results.values() if v is not None)
            return "OK" if ok_count >= needed else "ERR write_unavailable"
        else:
            for t in threads:
                t.join(timeout=self.op_timeout + 0.5)
            with results_lock:
                ok_count = sum(1 for v in results.values() if v is not None)
            if multi:
                return "OK" if ok_count >= 2 else "ERR write_unavailable"
            return "OK" if ok_count >= 1 else "ERR backend_unavailable"

    # --------------------------------------------------------- read path --
    def _do_read(self, key: str) -> str:
        if self.majority_read:
            return self._do_read_majority(key)
        return self._do_read_roundrobin(key)

    def _do_read_roundrobin(self, key: str) -> str:
        tried: set[str] = set()
        for _ in range(2):  # one retry against a different candidate
            candidates = [b for b in self._ready() if b.name not in tried]
            if not candidates:
                break
            b = self._rr_pick(candidates)
            tried.add(b.name)
            reply = b.call(f"GET {key}", self.op_timeout)
            if reply is None:
                b.up = False
                b.read_ready = False
                self.log(f"backend {b.name} appears DOWN")
                continue
            return reply
        return "ERR backend_unavailable"

    def _do_read_majority(self, key: str) -> str:
        candidates = self._ready()
        if not candidates:
            return "ERR backend_unavailable"

        results: dict[str, str] = {}
        results_lock = threading.Lock()

        def call_one(b: Backend) -> None:
            reply = b.call(f"GET {key}", self.op_timeout)
            if reply is None:
                b.up = False
                b.read_ready = False
                self.log(f"backend {b.name} appears DOWN")
                return
            with results_lock:
                results[b.name] = reply

        threads = [threading.Thread(target=call_one, args=(b,), daemon=True) for b in candidates]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=self.op_timeout + 0.5)

        if not results:
            return "ERR backend_unavailable"

        counts: dict[str, list[str]] = {}
        for name, reply in results.items():
            counts.setdefault(reply, []).append(name)

        total = len(results)
        majority_needed = total // 2 + 1
        winner = None
        for reply, names in counts.items():
            if len(names) >= majority_needed:
                winner = reply
                break

        if winner is None:
            return "ERR no_majority"

        for name, reply in results.items():
            if reply != winner:
                backend = next(b for b in candidates if b.name == name)
                if winner.startswith("VALUE "):
                    value = winner[len("VALUE "):]
                    backend.call(f"SET {key} {value}", self.op_timeout)
                elif winner == "NOT_FOUND":
                    backend.call(f"DEL {key}", self.op_timeout)
                self.log(f"repaired {name} for key '{key}' (had '{reply}', majority said '{winner}')")

        return winner

    # --------------------------------------------------------- dispatch --
    def _info(self) -> str:
        mode = "majority" if self.majority_read else "roundrobin"
        return (f"INFO backends={len(self.backends)} up={len(self._up())} "
                f"read_ready={len(self._ready())} read_mode={mode}")

    def dispatch(self, line: str) -> str:
        if not line.strip():
            return "ERR bad_command"
        parts = line.split(" ", 2)
        verb = parts[0].upper()

        if verb == "SET" and len(parts) == 3:
            return self._do_write("SET", parts[1], parts[2])

        if verb == "DEL" and len(parts) == 2:
            return self._do_write("DEL", parts[1], None)

        if verb == "GET" and len(parts) == 2:
            return self._do_read(parts[1])

        if verb == "INFO" and len(parts) == 1:
            return self._info()

        if verb == "PING" and len(parts) == 1:
            up = self._up()
            if not up:
                return "ERR backend_unavailable"
            b = self._rr_pick(up)
            reply = b.call("PING", self.op_timeout)
            return reply if reply is not None else "ERR backend_unavailable"

        return "ERR bad_command"

    # --------------------------------------------------- background loops --
    def _catch_up(self, backend: Backend) -> None:
        backend.catching_up = True
        try:
            sources = [b for b in self.backends if b is not backend and b.read_ready]
            if not sources:
                backend.read_ready = True
                self.log(f"{backend.name} back in the read rotation")
                return

            infos: list[tuple[Backend, float]] = []
            for s in sources:
                reply = s.call("INFO", self.op_timeout)
                if reply and reply.startswith("INFO "):
                    _, uptime_s, _count = reply.split(" ", 2)
                    infos.append((s, float(uptime_s)))
            if not infos:
                backend.read_ready = True
                self.log(f"{backend.name} back in the read rotation")
                return

            infos.sort(key=lambda pair: (-pair[1], pair[0].name))
            source, uptime = infos[0]
            self.log(f"catching {backend.name} up from {source.name} (uptime {uptime:.2f}s)")

            dump_reply = source.call("DUMP", self.op_timeout)
            if not dump_reply or not dump_reply.startswith("DUMP "):
                self.log(f"catch-up for {backend.name} failed: source DUMP unreachable")
                return
            snapshot = json.loads(dump_reply[len("DUMP "):])

            loaded = 0
            for k, v in snapshot.items():
                reply = backend.call(f"LOAD {k} {v}", self.op_timeout)
                if reply == "LOADED":
                    loaded += 1

            held_reply = backend.call("DUMP", self.op_timeout)
            held_count = len(json.loads(held_reply[len("DUMP "):])) if held_reply else 0

            self.log(f"{backend.name} catch-up done: {loaded}/{len(snapshot)} snapshot keys "
                      f"applied, {held_count} keys now held (source had {len(snapshot)} at snapshot time)")
            backend.read_ready = True
            self.log(f"{backend.name} back in the read rotation")
        finally:
            backend.catching_up = False

    def _health_check_loop(self) -> None:
        while True:
            for b in self.backends:
                reply = b.call("PING", self.health_timeout)
                if reply == "PONG":
                    was_up = b.up
                    b.up = True
                    if not b.ever_checked:
                        # cold start: nothing to catch up from yet
                        b.read_ready = True
                        b.ever_checked = True
                    elif not was_up:
                        self.log(f"backend {b.name} is back up")
                        if self.catchup and len(self.backends) >= 2 and not b.catching_up:
                            threading.Thread(target=self._catch_up, args=(b,), daemon=True).start()
                        else:
                            b.read_ready = True
                else:
                    if b.up:
                        self.log(f"backend {b.name} appears DOWN")
                    b.up = False
                    b.read_ready = False
                    b.ever_checked = True
            time.sleep(self.health_interval)

    # ---------------------------------------------------------- serving --
    def _handle_conn(self, sock: socket.socket) -> None:
        conn = LineConn(sock)
        try:
            while True:
                line = conn.read_line()
                reply = self.dispatch(line)
                conn.send_line(reply)
        except ConnectionClosed:
            pass
        finally:
            conn.close()

    def serve(self, host: str, port: int) -> None:
        threading.Thread(target=self._health_check_loop, daemon=True).start()

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((host, port))
        listener.listen(128)
        print(f"[proxy] listening on {host}:{port}, backends={[b.address for b in self.backends]}", flush=True)
        try:
            while True:
                sock, _addr = listener.accept()
                t = threading.Thread(target=self._handle_conn, args=(sock,), daemon=True)
                t.start()
        except KeyboardInterrupt:
            pass
        finally:
            listener.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Replicating KV proxy")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=7000)
    p.add_argument("--backends", required=True, help="comma-separated host:port list")
    p.add_argument("--op-timeout", type=float, default=1.0)
    p.add_argument("--health-interval", type=float, default=1.0)
    p.add_argument("--health-timeout", type=float, default=0.5)
    p.add_argument("--majority-read", action="store_true")
    p.add_argument("--quorum-write", action="store_true")
    p.add_argument("--no-catchup", action="store_true")
    args = p.parse_args()

    backends = parse_backends(args.backends)
    proxy = Proxy(
        backends=backends,
        op_timeout=args.op_timeout,
        health_interval=args.health_interval,
        health_timeout=args.health_timeout,
        majority_read=args.majority_read,
        quorum_write=args.quorum_write,
        catchup=not args.no_catchup,
    )
    proxy.serve(args.host, args.port)


if __name__ == "__main__":
    main()
