# Workflow

Exact commands for every stage — running it, poking at it by hand, and
watching it recover from failures you cause yourself. Everything here uses
only `python3` and (optionally) `nc`; nothing needs installing.

## Contents

- [Prerequisites](#prerequisites)
- [Stage 1 — one server, no proxy](#stage-1--one-server-no-proxy)
- [Stage 2 — proxy in front of one server](#stage-2--proxy-in-front-of-one-server)
- [Stage 3 — proxy in front of three](#stage-3--proxy-in-front-of-three)
- [Stage 4 — killing and restarting a copy](#stage-4--killing-and-restarting-a-copy)
- [Stage 5 — corrupting a copy](#stage-5--corrupting-a-copy)
- [Bonus — quorum writes](#bonus--quorum-writes)
- [Running the automated tests](#running-the-automated-tests)
- [Checking cluster status at any time](#checking-cluster-status-at-any-time)
- [Clean shutdown](#clean-shutdown)
- [Command-line flag reference](#command-line-flag-reference)
- [Troubleshooting](#troubleshooting)

## Prerequisites

- Python 3.9 or newer, standard library only.
- `nc` (netcat) if you want to drive things by hand instead of `client.py`
  — entirely optional, `client.py` speaks the identical protocol.
- All commands below assume you're in the directory containing
  `kvserver.py` / `proxy.py` / `client.py`.

## Stage 1 — one server, no proxy

```bash
python3 kvserver.py --port 7101
```

In another terminal:

```bash
nc 127.0.0.1 7101
```
```
SET user:42 alice
OK
GET user:42
VALUE alice
```

Or without `nc`:

```bash
python3 client.py --port 7101 --cmd "SET user:42 alice"
python3 client.py --port 7101 --cmd "GET user:42"
```

`Ctrl+C` the server when done.

## Stage 2 — proxy in front of one server

```bash
# terminal 1
python3 kvserver.py --port 7101

# terminal 2
python3 proxy.py --port 7000 --backends 127.0.0.1:7101

# terminal 3
python3 client.py --port 7000 --cmd "SET k v"
python3 client.py --port 7000 --cmd "GET k"
```

To see the "dead backend → fast error" behavior: `Ctrl+C` terminal 1, then
immediately try `GET k` again through the proxy (terminal 3). Expect
`ERR backend_unavailable` within about a second (bounded by
`--op-timeout`), not a hang.

## Stage 3 — proxy in front of three

```bash
# terminals 1-3
python3 kvserver.py --port 7101
python3 kvserver.py --port 7102
python3 kvserver.py --port 7103

# terminal 4
python3 proxy.py --port 7000 --backends 127.0.0.1:7101,127.0.0.1:7102,127.0.0.1:7103
```

```bash
# terminal 5
python3 client.py --port 7000 --cmd "SET cart:9 2xbook"     # OK -- all three got it
```

Kill one backend (`Ctrl+C` in its terminal, or `kill <pid>`):

```bash
python3 client.py --port 7000 --cmd "SET cart:9 3xbook"     # still OK -- 2 of 3 up
```

Kill a second:

```bash
python3 client.py --port 7000 --cmd "SET cart:9 4xbook"     # ERR write_unavailable
python3 client.py --port 7000 --cmd "GET cart:9"            # VALUE 3xbook -- reads still work
```

To see reads spreading across backends, tag each one with a distinguishing
value first (`SET whoami 7101` sent directly to each backend's own port),
then issue several `GET whoami` through the proxy and watch the answer
rotate.

## Stage 4 — killing and restarting a copy

Continue from the Stage 3 cluster (all three up), or start fresh:

```bash
python3 client.py --port 7000 --cmd "SET key1 val1"
python3 client.py --port 7000 --cmd "SET key2 val2"
```

Kill kv-3 (`Ctrl+C` its terminal), wait a couple of seconds for the health
check to notice (`proxy.py`'s own stdout will print
`[proxy] backend kv-3 appears DOWN`), then write more data while it's still
down:

```bash
python3 client.py --port 7000 --cmd "SET key3 val3"    # only kv-1/kv-2 get this
```

Now bring kv-3 back as a **genuinely fresh process** (this matters — its map
starts empty and its uptime resets to 0, which is the whole point):

```bash
python3 kvserver.py --port 7103
```

Watch the proxy's own terminal — within one `--health-interval` you should
see something like:

```
[proxy] backend kv-3 is back up
[proxy] catching kv-3 up from kv-1 (uptime NN.NNs)
[proxy] kv-3 catch-up done: 3/3 snapshot keys applied, 3 keys now held (source had 3 at snapshot time)
[proxy] kv-3 back in the read rotation
```

Confirm directly against kv-3's own port (bypassing the proxy) that it now
has everything, including `key3` which it never saw live:

```bash
python3 client.py --port 7103 --cmd "GET key1"
python3 client.py --port 7103 --cmd "GET key3"
```

To specifically provoke the "live write during catch-up" race described on
Plate 4: kill kv-3, restart it, and *immediately* (within the same second,
before the catch-up log lines appear) send a `SET` for a key through the
proxy. If your timing lands inside the catch-up window, the log will show
`SKIPPED` for that key during the snapshot replay (meaning the live write
already got there first) rather than `LOADED`.

## Stage 5 — corrupting a copy

Start the proxy with `--majority-read` this time:

```bash
python3 proxy.py --port 7000 --backends 127.0.0.1:7101,127.0.0.1:7102,127.0.0.1:7103 --majority-read
```

```bash
python3 client.py --port 7000 --cmd "SET user:42 alice"

# CORRUPT goes straight to one backend's own port, bypassing the proxy entirely
python3 client.py --port 7103 --cmd "CORRUPT user:42 al?ce"

# read through the proxy: majority (kv-1 + kv-2) outvotes kv-3
python3 client.py --port 7000 --cmd "GET user:42"     # VALUE alice

# a moment later, ask kv-3 directly -- it should have been quietly repaired
python3 client.py --port 7103 --cmd "GET user:42"     # VALUE alice
```

Watch the proxy's stdout for the repair log line:
`[proxy] repaired kv-3 for key 'user:42' (had 'VALUE al?ce', majority said 'VALUE alice')`.

To see `ERR no_majority`: `CORRUPT` all three backends to three *different*
values directly, then `GET` through the proxy.

## Bonus — quorum writes

```bash
python3 proxy.py --port 7000 --backends 127.0.0.1:7101,127.0.0.1:7102,127.0.0.1:7103 --quorum-write
```

Behaves identically to Stage 3 under normal conditions; the difference only
shows up when one backend is slow (not down — down is still subject to the
"need 2 up" rule before anything is even attempted). There's no built-in way
to inject artificial slowness from the CLI, so this is easiest to observe by
reading `proxy.py`'s `_do_write()` or by temporarily lowering `--op-timeout`
to something very small against a healthy cluster and watching writes still
succeed once a majority (not all three) respond within that window.

## Running the automated tests

```bash
python3 test_kvstore.py
```

Spins up real subprocesses and real sockets for each of the 14 tests (no
mocks), covering all five stages plus the quorum-write bonus, then tears
them down. Takes roughly 30–60 seconds total; a healthy run ends with:

```
14 passed, 0 failed
```

If a test fails, the relevant subprocess's combined stdout/stderr is
available via that test's `Proc.output()` — the tests are written so each
failure's `assert` message includes enough context (the actual reply
received) to diagnose without re-running under a debugger.

## Checking cluster status at any time

`INFO` sent to the *proxy* (not a backend) at any point returns its current
belief about the cluster:

```bash
python3 client.py --port 7000 --cmd "INFO"
# INFO backends=3 up=3 read_ready=3 read_mode=roundrobin
```

`INFO` sent to a *backend* directly returns that backend's own uptime and
key count (also what Stage 4's catch-up logic uses internally):

```bash
python3 client.py --port 7103 --cmd "INFO"
# INFO 42.117 6
```

## Clean shutdown

`Ctrl+C` each process, or `kill` the PIDs — every listener is a plain TCP
socket with `SO_REUSEADDR` set, so restarting on the same port immediately
after works without a `TIME_WAIT` delay. Nothing is written to disk, so
there's no cleanup beyond stopping the processes.

## Command-line flag reference

**`kvserver.py`**

| Flag | Default | Meaning |
|---|---|---|
| `--host` | `127.0.0.1` | Listen address. |
| `--port` | *(required)* | Listen port. |

**`proxy.py`**

| Flag | Default | Meaning |
|---|---|---|
| `--host` | `127.0.0.1` | Listen address for clients. |
| `--port` | `7000` | Listen port for clients. |
| `--backends` | *(required)* | Comma-separated `host:port` list. One entry = Stage 2 behavior; two or more = Stage 3+ rules apply. |
| `--op-timeout` | `1.0` | Seconds to wait for a single backend call before treating it as failed. |
| `--health-interval` | `1.0` | Seconds between health-check `PING`s to each backend. |
| `--health-timeout` | `0.5` | Seconds to wait for a health-check `PONG` before declaring that tick a miss. |
| `--majority-read` | off | Stage 5: vote across all ready backends on every `GET`, repairing disagreements. |
| `--quorum-write` | off | Bonus: acknowledge a write once a majority of the backends it was sent to confirm, instead of waiting for all of them. |
| `--no-catchup` | catch-up **on** | Disables Stage 4's automatic catch-up of a recovered backend (it will rejoin the read rotation immediately instead, with whatever stale data it had). |

## Troubleshooting

- **`OSError: [Errno 98] Address already in use`** — something is still
  bound to that port. `SO_REUSEADDR` handles the common `TIME_WAIT` case,
  so this almost always means a previous process is still actually running;
  find and kill it (`pgrep -fa kvserver.py`, `pgrep -fa proxy.py`).
- **Writes hang instead of returning quickly** — check `--op-timeout`
  wasn't set unreasonably high; the default (1s) bounds every individual
  backend call.
- **A restarted backend never rejoins the read rotation** — check the
  proxy's own stdout for `catching kv-N up from ...` — if the chosen source
  backend was itself unreachable mid-copy, the log will say the `DUMP`
  failed and the recovering backend is deliberately left out of the read
  rotation rather than serving an incomplete copy; it will retry on the next
  down→up transition, or simply restart the proxy against the (still
  correct) backends.
