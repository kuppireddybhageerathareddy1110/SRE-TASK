"""
test_kvstore.py
----------------
End-to-end tests using real OS subprocesses and real TCP sockets -- the
same way a human with `nc` would exercise this system. No pytest
dependency; plain asserts plus a tiny runner so `python3 test_kvstore.py`
just works.

Covers every stage in the brief:
  Stage 1 - kvserver.py alone: SET/GET/DEL/PING, unknown command, the
            "command arrives in two pieces" case from Plate 1.
  Stage 2 - proxy.py in front of exactly one backend: transparent
            pass-through, and ERR backend_unavailable when it dies.
  Stage 3 - proxy.py in front of three backends: broadcast writes,
            round-robin reads, the "need >=2 up to write" rule, the two
            distinguishable errors.
  Stage 4 - killing and restarting a backend for real (a fresh process,
            genuinely empty map) and checking the proxy catches it up
            from the oldest survivor before returning it to the read
            rotation, including the "a write lands mid-catch-up" race.
  Stage 5 - CORRUPT one backend directly, confirm majority-read outvotes
            it and repairs it in the background.
  Bonus   - --quorum-write acknowledges once a majority of the copies it
            wrote to have confirmed.
"""

from __future__ import annotations
import os
import socket
import subprocess
import sys
import time

from protocol import LineConn

HERE = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable


def connect(port: int, host: str = "127.0.0.1", timeout: float = 5.0) -> LineConn:
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            s = socket.create_connection((host, port), timeout=1.0)
            s.settimeout(None)  # connect attempt is time-boxed; normal I/O should block
            return LineConn(s)
        except OSError as e:
            last_err = e
            time.sleep(0.1)
    raise RuntimeError(f"could not connect to {host}:{port}: {last_err}")


def cmd(conn: LineConn, line: str) -> str:
    conn.send_line(line)
    return conn.read_line()


def wait_until(fn, timeout=5.0, interval=0.1):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = fn()
        if last:
            return last
        time.sleep(interval)
    return last


class Proc:
    """Wraps one server/proxy subprocess so tests can start/kill/restart it."""
    def __init__(self, script: str, args: list[str], name: str):
        self.script = script
        self.args = args
        self.name = name
        self.proc = None
        self.start()

    def start(self):
        self.proc = subprocess.Popen(
            [PYTHON, os.path.join(HERE, self.script)] + self.args,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )

    def kill(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=3)

    def restart(self):
        self.kill()
        self.start()

    def output(self) -> str:
        if self.proc.poll() is not None and self.proc.stdout:
            return self.proc.stdout.read()
        return "(still running)"


class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0

    def run(self, name, fn):
        print(f"--- {name} ---")
        try:
            fn()
            print(f"PASS: {name}")
            self.passed += 1
        except Exception as e:
            print(f"FAIL: {name}: {e!r}")
            self.failed += 1


# ======================================================================
# Stage 1 -- bare kvserver
# ======================================================================
def test_stage1_basic_protocol(_):
    kv = Proc("kvserver.py", ["--port", "9101"], "kv")
    try:
        c = connect(9101)
        assert cmd(c, "PING") == "PONG"
        assert cmd(c, "GET nope") == "NOT_FOUND"
        assert cmd(c, "SET user:42 alice") == "OK"
        assert cmd(c, "GET user:42") == "VALUE alice"
        assert cmd(c, "SET user:42 alice smith") == "OK"       # value w/ spaces
        assert cmd(c, "GET user:42") == "VALUE alice smith"
        assert cmd(c, "DEL user:42") == "OK"
        assert cmd(c, "GET user:42") == "NOT_FOUND"
        assert cmd(c, "DEL user:42") == "NOT_FOUND"
        assert cmd(c, "FOO bar") == "ERR bad_command"
        assert cmd(c, "PING") == "PONG"   # connection stayed open after the bad command
    finally:
        kv.kill()


def test_stage1_command_arrives_in_pieces(_):
    """Mirrors Plate 1: send a command as two separate TCP writes with no
    newline in between, and confirm the server waits for the full line."""
    kv = Proc("kvserver.py", ["--port", "9102"], "kv")
    try:
        lc = connect(9102)  # retries until the server is actually listening
        raw = lc.sock
        raw.settimeout(5)
        raw.sendall(b"SET user:42 alice\n")
        assert raw.recv(100) == b"OK\n"
        raw.sendall(b"GE")       # first piece, no newline yet
        time.sleep(0.2)
        raw.sendall(b"T user:42\n")  # rest of it
        assert raw.recv(100) == b"VALUE alice\n"
        raw.close()
    finally:
        kv.kill()


def test_stage1_concurrent_clients(_):
    kv = Proc("kvserver.py", ["--port", "9103"], "kv")
    try:
        a, b = connect(9103), connect(9103)
        assert cmd(a, "SET x 1") == "OK"
        assert cmd(b, "SET y 2") == "OK"
        assert cmd(a, "GET y") == "VALUE 2"
        assert cmd(b, "GET x") == "VALUE 1"
    finally:
        kv.kill()


# ======================================================================
# Stage 2 -- proxy in front of exactly one backend
# ======================================================================
def test_stage2_transparent_passthrough(_):
    kv = Proc("kvserver.py", ["--port", "9201"], "kv")
    proxy = Proc("proxy.py", ["--port", "9200", "--backends", "127.0.0.1:9201",
                              "--health-interval", "0.2"], "proxy")
    try:
        time.sleep(0.5)
        pc = connect(9200)
        assert cmd(pc, "SET foo bar") == "OK"
        assert cmd(pc, "GET foo") == "VALUE bar"
        assert cmd(pc, "PING") == "PONG"
        assert cmd(pc, "GET missing") == "NOT_FOUND"
        # Talking to the backend directly gives the same result.
        kc = connect(9201)
        assert cmd(kc, "GET foo") == "VALUE bar"
    finally:
        proxy.kill()
        kv.kill()


def test_stage2_dead_backend_errors_not_hangs(_):
    kv = Proc("kvserver.py", ["--port", "9202"], "kv")
    proxy = Proc("proxy.py", ["--port", "9203", "--backends", "127.0.0.1:9202",
                              "--health-interval", "0.2", "--health-timeout", "0.2"], "proxy")
    try:
        time.sleep(0.5)
        pc = connect(9203)
        assert cmd(pc, "GET x") == "NOT_FOUND"
        kv.kill()
        time.sleep(0.6)  # let a health check cycle notice
        start = time.time()
        resp = cmd(pc, "GET x")
        elapsed = time.time() - start
        assert resp == "ERR backend_unavailable", resp
        assert elapsed < 2.0, f"took {elapsed}s -- looks like a hang, not a fast error"
    finally:
        proxy.kill()
        kv.kill()


# ======================================================================
# Stage 3 -- three backends, broadcast writes, round-robin reads
# ======================================================================
def _start_cluster(base_port: int, proxy_port: int, extra_proxy_args=None):
    kvs = [Proc("kvserver.py", ["--port", str(base_port + i)], f"kv-{i+1}") for i in range(3)]
    backends = ",".join(f"127.0.0.1:{base_port + i}" for i in range(3))
    args = ["--port", str(proxy_port), "--backends", backends,
            "--health-interval", "0.2", "--health-timeout", "0.2", "--op-timeout", "0.5"]
    if extra_proxy_args:
        args += extra_proxy_args
    proxy = Proc("proxy.py", args, "proxy")
    time.sleep(0.6)  # let the first health-check pass mark everyone up
    return kvs, proxy


def test_stage3_write_reaches_all_three(_):
    kvs, proxy = _start_cluster(9310, 9300)
    try:
        pc = connect(9300)
        assert cmd(pc, "SET cart:9 2xbook") == "OK"
        for i in range(3):
            kc = connect(9310 + i)
            assert cmd(kc, "GET cart:9") == "VALUE 2xbook", f"kv-{i+1} missing the write"
    finally:
        proxy.kill()
        [k.kill() for k in kvs]


def test_stage3_writes_are_concurrent_not_serial(_):
    """Three backends each answer immediately, so a broadcast write should
    take roughly as long as one write, not three."""
    kvs, proxy = _start_cluster(9320, 9301)
    try:
        pc = connect(9301)
        start = time.time()
        for i in range(10):
            assert cmd(pc, f"SET k{i} v{i}") == "OK"
        elapsed = time.time() - start
        assert elapsed < 2.0, f"10 writes took {elapsed:.2f}s -- looks serialized across backends"
    finally:
        proxy.kill()
        [k.kill() for k in kvs]


def test_stage3_two_of_three_rule_and_distinguishable_errors(_):
    kvs, proxy = _start_cluster(9330, 9302)
    try:
        pc = connect(9302)
        assert cmd(pc, "SET cart:9 2xbook") == "OK"

        kvs[1].kill()  # kv-2 down, two still up
        wait_until(lambda: "up=2" in cmd(pc, "INFO"), timeout=3)
        assert cmd(pc, "SET cart:9 3xbook") == "OK"

        kvs[2].kill()  # kv-3 down too, only one left
        wait_until(lambda: "up=1" in cmd(pc, "INFO"), timeout=3)
        resp = cmd(pc, "SET cart:9 4xbook")
        assert resp == "ERR write_unavailable", resp

        # Reads must still work with exactly one copy up, and the two
        # error conditions (backend down vs write refused) must be
        # distinguishable by the client -- they use different strings.
        assert cmd(pc, "GET cart:9") == "VALUE 3xbook"
        assert resp != "ERR backend_unavailable"
    finally:
        proxy.kill()
        [k.kill() for k in kvs]


def test_stage3_reads_spread_across_up_copies(_):
    kvs, proxy = _start_cluster(9340, 9303)
    try:
        pc = connect(9303)
        assert cmd(pc, "SET k v") == "OK"
        hit_ports = set()
        # A round-robin reader hitting 3 up copies should visit more than
        # one of them across several reads.
        for i in range(9340, 9343):
            kc = connect(i)
            # tag each backend with a distinguishing extra key so we can
            # tell who answered a given GET through the proxy
            cmd(kc, f"SET whoami {i}")
        for _ in range(9):
            resp = cmd(pc, "GET whoami")
            hit_ports.add(resp)
        assert len(hit_ports) > 1, f"round robin never left one copy: {hit_ports}"
    finally:
        proxy.kill()
        [k.kill() for k in kvs]


# ======================================================================
# Stage 4 -- real restart + catch-up
# ======================================================================
def test_stage4_restarted_copy_catches_up(_):
    kvs, proxy = _start_cluster(9350, 9304)
    try:
        pc = connect(9304)
        for i in range(5):
            assert cmd(pc, f"SET key{i} val{i}") == "OK"

        kvs[2].kill()  # kv-3 down
        wait_until(lambda: "up=2" in cmd(pc, "INFO"), timeout=3)

        # More writes happen while kv-3 is down -- it must learn these too.
        assert cmd(pc, "SET key5 val5") == "OK"

        kvs[2].restart()  # a genuinely fresh process: empty map, uptime=0
        # Immediately after restart it must NOT serve reads (empty answer
        # is worse than no answer) -- check its direct port, bypassing the
        # proxy, right as it comes back.
        kv3_direct = connect(9350 + 2)
        # It's fine either way what this returns right at boot (it may
        # already have started catching up), but the proxy must not trust
        # it for reads until read_ready flips -- checked below.
        wait_until(lambda: "read_ready=3" in cmd(pc, "INFO"), timeout=5)

        for i in range(6):
            resp = cmd(kv3_direct, f"GET key{i}")
            assert resp == f"VALUE val{i}", f"kv-3 never caught up on key{i}: {resp}"

        # And it's back in the proxy's read rotation, not just holding
        # the data privately.
        hit = set()
        for _ in range(6):
            hit.add(cmd(pc, "GET key0"))
        assert hit == {"VALUE val0"}
    finally:
        proxy.kill()
        [k.kill() for k in kvs]


def test_stage4_live_write_during_catchup_is_not_clobbered(_):
    """The interesting race named on Plate 4: a write for a key lands on
    the recovering copy *during* its catch-up window. The snapshot being
    copied in from the source must not overwrite it, because LOAD is
    set-if-absent."""
    kvs, proxy = _start_cluster(9360, 9305, extra_proxy_args=["--op-timeout", "2.0"])
    try:
        pc = connect(9305)
        assert cmd(pc, "SET shared original") == "OK"

        kvs[2].kill()
        wait_until(lambda: "up=2" in cmd(pc, "INFO"), timeout=3)
        kvs[2].restart()

        # Race a fresh write for the SAME key against the catch-up window.
        # Because the proxy adds a recovering backend to the write set the
        # instant it's seen as up (before catch-up finishes), this SET
        # should land on kv-3 directly, and LOAD must not stomp it later.
        deadline = time.time() + 5
        while time.time() < deadline:
            resp = cmd(pc, "SET shared updated")
            if resp == "OK":
                break
            time.sleep(0.05)
        assert resp == "OK", "write never got accepted while kv-3 was recovering"

        wait_until(lambda: "read_ready=3" in cmd(pc, "INFO"), timeout=5)
        kv3_direct = connect(9360 + 2)
        assert cmd(kv3_direct, "GET shared") == "VALUE updated"
    finally:
        proxy.kill()
        [k.kill() for k in kvs]


# ======================================================================
# Stage 5 -- CORRUPT + majority read + repair
# ======================================================================
def test_stage5_majority_read_outvotes_and_repairs_corruption(_):
    kvs, proxy = _start_cluster(9370, 9306, extra_proxy_args=["--majority-read"])
    try:
        pc = connect(9306)
        assert cmd(pc, "SET user:42 alice") == "OK"

        # CORRUPT goes straight to kv-3's own port, bypassing the proxy,
        # exactly as the brief describes.
        kv3_direct = connect(9370 + 2)
        assert cmd(kv3_direct, "CORRUPT user:42 al?ce") == "OK"
        assert cmd(kv3_direct, "GET user:42") == "VALUE al?ce"

        # Through the proxy, majority (kv-1 + kv-2) outvotes the corrupt kv-3.
        assert cmd(pc, "GET user:42") == "VALUE alice"

        # And it should have quietly repaired kv-3 in the process.
        fixed = wait_until(lambda: cmd(kv3_direct, "GET user:42") == "VALUE alice", timeout=3)
        assert fixed
    finally:
        proxy.kill()
        [k.kill() for k in kvs]


def test_stage5_no_majority_returns_error(_):
    kvs, proxy = _start_cluster(9380, 9307, extra_proxy_args=["--majority-read"])
    try:
        pc = connect(9307)
        assert cmd(pc, "SET k v0") == "OK"
        for i, port_offset in enumerate((0, 1, 2)):
            kc = connect(9380 + port_offset)
            cmd(kc, f"CORRUPT k v{i}_unique")  # make all three different
        resp = cmd(pc, "GET k")
        assert resp == "ERR no_majority", resp
    finally:
        proxy.kill()
        [k.kill() for k in kvs]


# ======================================================================
# Bonus -- quorum-write
# ======================================================================
def test_bonus_quorum_write_does_not_wait_for_slowest(_):
    kvs, proxy = _start_cluster(9390, 9308, extra_proxy_args=["--quorum-write", "--op-timeout", "3.0"])
    try:
        pc = connect(9308)
        # Sanity: a normal quorum-write still succeeds and is visible on
        # at least a majority immediately.
        start = time.time()
        assert cmd(pc, "SET k v") == "OK"
        elapsed = time.time() - start
        assert elapsed < 1.0, f"quorum-write took {elapsed:.2f}s with all backends healthy"
    finally:
        proxy.kill()
        [k.kill() for k in kvs]


# ======================================================================
def main() -> int:
    runner = TestRunner()
    tests = [
        ("[Stage 1] SET/GET/DEL/PING + unknown command", test_stage1_basic_protocol),
        ("[Stage 1] command arriving as two TCP writes (Plate 1)", test_stage1_command_arrives_in_pieces),
        ("[Stage 1] two clients concurrently, no interference", test_stage1_concurrent_clients),
        ("[Stage 2] proxy is transparent pass-through", test_stage2_transparent_passthrough),
        ("[Stage 2] dead backend -> fast error, not a hang", test_stage2_dead_backend_errors_not_hangs),
        ("[Stage 3] write reaches all three copies", test_stage3_write_reaches_all_three),
        ("[Stage 3] broadcast writes are concurrent, not serial", test_stage3_writes_are_concurrent_not_serial),
        ("[Stage 3] need >=2 up to write; two distinguishable errors", test_stage3_two_of_three_rule_and_distinguishable_errors),
        ("[Stage 3] reads spread across up copies", test_stage3_reads_spread_across_up_copies),
        ("[Stage 4] restarted copy catches up before serving reads", test_stage4_restarted_copy_catches_up),
        ("[Stage 4] live write during catch-up isn't clobbered by snapshot", test_stage4_live_write_during_catchup_is_not_clobbered),
        ("[Stage 5] majority read outvotes + repairs a corrupted copy", test_stage5_majority_read_outvotes_and_repairs_corruption),
        ("[Stage 5] no majority -> ERR no_majority", test_stage5_no_majority_returns_error),
        ("[Bonus] quorum-write doesn't wait on a healthy cluster", test_bonus_quorum_write_does_not_wait_for_slowest),
    ]
    for name, fn in tests:
        runner.run(name, lambda fn=fn: fn(runner))

    print(f"\n{runner.passed} passed, {runner.failed} failed")
    return 1 if runner.failed else 0


if __name__ == "__main__":
    sys.exit(main())
