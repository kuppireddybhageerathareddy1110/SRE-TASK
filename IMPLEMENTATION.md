# Implementation notes

Deeper technical detail than the README: concurrency model, locking, data
structures, and the edge cases each piece of code exists to handle. Written
for someone reading the source, not running it.

## Contents

- [File-by-file](#file-by-file)
- [Concurrency model](#concurrency-model)
- [Locking strategy](#locking-strategy)
- [Data structures](#data-structures)
- [Error taxonomy](#error-taxonomy)
- [Why threads, not asyncio](#why-threads-not-asyncio)
- [Why one persistent connection per backend, not one-per-call](#why-one-persistent-connection-per-backend-not-one-per-call)
- [A real bug, and the lesson from it](#a-real-bug-and-the-lesson-from-it)

---

## File-by-file

**`protocol.py`** — `LineConn` wraps a `socket.socket` and exposes
`read_line()` / `send_line()`. Internally it keeps a `bytes` buffer per
connection; `read_line()` calls `recv()` in a loop, appending to the buffer,
until a `\n` shows up, then slices off and returns everything before it,
keeping the remainder for next time. A `recv()` that returns `b""` means the
peer closed the socket (TCP's "zero-byte read = EOF" signal) — that's
surfaced as a `ConnectionClosed` exception rather than an empty string, so
callers can't accidentally treat "peer hung up" as "peer sent an empty
line." This one class is used by every TCP link in the system: client↔
kvserver, client↔proxy, and proxy↔backend — same framing problem, one fix.

**`kvserver.py`** — `KVServer` holds one `dict[str, str]` behind one
`threading.RLock`. No knowledge of proxies, replication, or any other copy
of itself exists in this file at all — that's deliberate (see
[Concurrency model](#concurrency-model)). `_dispatch()` is a single
`if/elif` chain over the verb; every branch does one lock-guarded dict
operation and writes one reply line. `_handle_conn()` is the accept-loop
body, run on its own thread per connection.

**`proxy.py`** — the only file that knows more than one backend exists.
- `Backend` — one persistent TCP link to one `kvserver.py`, plus the belief
  state about it (`up`, `read_ready`, `catching_up`) and a lock serializing
  access to that one link (see [Locking strategy](#locking-strategy)).
- `Proxy` — everything else: the write fan-out, the two read strategies, the
  health-check loop, and the catch-up procedure. `_dispatch()` mirrors
  `kvserver.py`'s but adds the proxy-only branches (`SET`/`DEL` broadcast,
  `GET` routing, `INFO` about proxy state) and falls through to a raw
  pass-through of anything else to one backend — which is *all* Stage 2 is:
  the same fallback branch, just with only one backend configured.

**`client.py`** — no logic beyond "connect, then either run one `--cmd` and
print the reply, or loop reading lines from stdin." Exists so testing by
hand doesn't require typing raw `nc` sessions every time, though `nc` works
identically against either server.

**`test_kvstore.py`** — spins up real `kvserver.py` / `proxy.py`
subprocesses with `subprocess.Popen` and drives them over real sockets. No
mocking of the network or the process boundary, because the entire point of
this exercise is what happens when a *real* process disappears — a mock
can't disappear.

---

## Concurrency model

**Thread per connection**, everywhere, exactly as the brief's hint suggests.
Each accepted socket gets its own `threading.Thread(daemon=True)` running a
`while True: read_line() -> dispatch() -> send_line()` loop. This is true
in `kvserver.py` for client connections, and in `proxy.py` for both client
connections *and* the concurrent per-backend calls a single write or
majority-read fans out to.

**Backends know nothing about each other, or about being backends at all.**
`kvserver.py` has zero code path that behaves differently depending on
whether a proxy or a bare `nc` is on the other end of the socket. All
replication intelligence — who's up, what to broadcast, who to trust — lives
in `proxy.py`, which holds no data of its own. This wasn't the first design
tried (see [the postmortem](#a-real-bug-and-the-lesson-from-it) below) but
it's the one that matches the brief's own architecture (Plate 0: three
identical boxes, one smart proxy) and it's considerably simpler to reason
about: there is exactly one place decisions get made.

**Fan-out uses one thread per target, joined (or polled) before replying.**
`_do_write()` and `_do_read_majority()` both spawn one `threading.Thread`
per backend they need to contact and either `.join()` all of them (default
write mode, full majority-read) or poll a shared `results` dict until enough
have answered (`--quorum-write` mode, which only needs a majority, not
everyone). This is what makes a 3-way broadcast cost about as long as the
slowest single backend, not three sequential round-trips — directly tested
in `test_stage3_writes_are_concurrent_not_serial`.

---

## Locking strategy

Three distinct locks, each guarding a different thing, deliberately kept
separate so unrelated operations never contend:

1. **`KVServer._lock`** (`RLock`) — guards the one `dict`. Every `get`/`set`/
   `delete`/`dump`/`key_count` call takes it for the duration of a single
   dict operation. Reentrant (`RLock` not `Lock`) because `set_if_absent`
   (used by `LOAD`) and a couple of other helpers call other locked methods
   internally in earlier iterations of this code — kept as `RLock` since
   it's free and removes a class of future foot-guns.

2. **`Backend.lock`** — guards that one backend's single persistent
   `LineConn`. Every `Backend.call()` (used for health-check `PING`s,
   broadcast writes, reads, `INFO`/`DUMP`/`LOAD` during catch-up — literally
   every proxy→backend interaction) takes this lock for the round trip of
   one request/response. This matters because a single TCP connection can't
   safely have two threads both writing to it and both reading from it at
   the same time without their bytes interleaving — the lock turns "one
   persistent connection, many client threads that might all want to talk
   to this backend at once" into "each request to this backend happens
   atomically, in some order." The cost is that two client requests hitting
   the same backend at the same moment serialize *for that backend only* —
   other backends aren't affected, since each has its own lock.

3. **`Proxy._rr_lock`** — guards nothing but the round-robin counter used by
   `_rr_pick()`. Tiny, held for microseconds, exists purely so two
   concurrent `GET`s can't both read-then-increment the same counter value
   and land on the same backend when they should have been spread apart.

Nothing in this system ever needs to hold two of these locks at once — no
lock-ordering to get wrong, no deadlock risk between them.

---

## Data structures

```python
# kvserver.py
KVServer._data: dict[str, str]        # the actual store
KVServer._lock: threading.RLock       # guards it
KVServer._start_time: float           # set once at boot; INFO's uptime = now - this

# proxy.py
Backend.address: (host, port)
Backend.conn: LineConn | None         # None when currently disconnected
Backend.lock: threading.Lock          # serializes access to .conn
Backend.up: bool                      # eligible for writes / counted for the "2 up" rule
Backend.read_ready: bool              # eligible for reads (false while catching_up)
Backend.catching_up: bool             # true only during an in-flight Stage 4 copy

Proxy.backends: list[Backend]
Proxy._rr_index: int                  # shared round-robin cursor
Proxy._rr_lock: threading.Lock
```

`up` and `read_ready` are deliberately two separate booleans, not one
"status" enum — a backend spends real, observable time with `up=True,
read_ready=False` (mid catch-up), and collapsing that into a single status
field would force some other part of the code to keep re-deriving "but is it
allowed to answer reads *right now*" from a state machine instead of just
reading a flag.

---

## Error taxonomy

Three distinct proxy-generated error strings, each meaning something a
client could plausibly want to branch on:

| Error | Fires when | Distinguishes from |
|---|---|---|
| `ERR bad_command` | Malformed or unrecognized command — identical in `kvserver.py` and `proxy.py`. | A protocol-level mistake, nothing to do with backend health. |
| `ERR backend_unavailable` | Zero backends are currently reachable to answer this request at all (read *or* write; Stage 2's single-backend case is just the N=1 instance of this). | "The system is down" vs. "the system is up but said no." |
| `ERR write_unavailable` | At least one backend is reachable, but fewer than two are up, so the Stage 3 write rule refuses to even attempt the write. | Distinct from `backend_unavailable` specifically so a client can tell "nothing's there" apart from "something's there, but policy said no" — this is the pair of "tellable apart" errors the brief asks for. |
| `ERR no_majority` | Stage 5 only: every backend that answered gave a different value, so there's no majority to trust. | A vote that was *taken* and came back inconclusive, vs. a vote that couldn't be taken at all. |

`ERR read_unavailable` does **not** exist — an earlier draft invented it as
a fourth string for "no backend can serve this read," before noticing the
brief's own Plate 2 transcript already names that exact condition
`ERR backend_unavailable`. Reusing the brief's name instead of inventing a
new one is the correct call once you notice the overlap.

---

## Why threads, not asyncio

The brief explicitly allows either ("Threads, async, or processes? Any of
them."). Threads were chosen because:

- The whole system is I/O-bound on small, sequential request/response pairs
  — no workload here benefits from asyncio's single-thread cooperative
  scheduling the way, say, thousands of idle long-lived connections would.
- A thread-per-connection accept loop is what the brief's own pseudocode on
  Plate/Stage 1 sketches, and matches the mental model of "one backend call
  = one blocking round trip" used throughout the write fan-out and
  majority-read code — `b.call(line, timeout)` reads as ordinary synchronous
  code because it *is* ordinary synchronous code, just running on its own
  thread. The equivalent asyncio version wouldn't be meaningfully shorter
  and would trade this straightforwardness for `async`/`await` coloring
  through every call site.
- Python's GIL is a non-issue here: every thread spends essentially all its
  time blocked in `socket.recv()`/`send()`, not doing CPU work, which is
  exactly the situation the GIL doesn't penalize.

## Why one persistent connection per backend, not one-per-call

`Backend` keeps a single long-lived `LineConn` and reuses it for every
`PING`, `SET`, `GET`, `INFO`, `DUMP`, and `LOAD` sent to that backend,
rather than opening a fresh TCP connection per call. Reconnecting every call
would work too, but:

- It would make the health-check loop's job — "is this backend currently
  reachable" — indistinguishable from "can I complete a fresh TCP handshake
  right now," which is a slightly different (and slower to detect) question
  than "is the connection I already trust still alive."
- It roughly triples the syscalls (and, on some backend implementations,
  the TCP handshake latency) per operation for no benefit here, since a
  single proxy talking to a fixed, small set of backends is exactly the case
  connection reuse exists for.

The cost — the `Backend.lock` serialization mentioned above — is small,
since request/response pairs against an in-memory store are fast.

---

## A real bug, and the lesson from it

Worth documenting because it's a genuinely easy trap. An earlier version of
this system (a leader/follower design, later discarded in favor of the
proxy+dumb-backends architecture the brief actually describes) had a
replication stream line that looked like:

```
OP 1 SET k1 v1
```

parsed with:

```python
parts = line.split(" ", 3)          # ["OP", "1", "SET", "k1 v1"]
sub = parts[2]                      # "SET"  <-- bug: dropped "k1 v1" entirely
```

`maxsplit=3` splits on the *first three spaces*, which — for a 4-token line
— separates every token, leaving nothing extra in the last slot for `parts[2]`
to accidentally include. The fix that survived into the final design:
split off only the fields you need a fixed count of (`verb`, `key`), and let
the *value* be "everything else, unsplit":

```python
parts = line.split(" ", 2)          # ["SET", "key", "the rest of the line"]
```

This is why `kvserver.py`'s and `proxy.py`'s command parsers all use
`maxsplit=2` (or `1` where only a verb+rest exists, like `HELLO`-style admin
replies) rather than a fixed count matching the "expected" number of
fields — the value (or JSON payload, in `DUMP`'s case) is exactly the kind
of field that can itself contain the delimiter you're splitting on, and
`str.split(sep, n)`'s `n` counts *splits*, not *fields*, which is the
off-by-one that's easy to get backwards under time pressure.
