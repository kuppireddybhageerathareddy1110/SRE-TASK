# Replicated Key-Value Store over TCP

A proxy in front of N plain, independent in-memory key-value servers. Writes
broadcast to every server that's up; reads are served by one (or, in Stage
5, voted on across all of them). No consensus library, no database, no
external dependencies — just sockets, threads, and a `dict` guarded by a
lock.

```
Clients --TCP--> Proxy :7000 --broadcast writes--> kv-1 :7101
                              --round-robin reads--> kv-2 :7102
                                                      kv-3 :7103
```

Stages 1–3 (core) and 4–5 (stretch) are all implemented and tested. See
[`TRANSCRIPTS`](#terminal-transcripts-real-output) below for real `nc`
sessions against the running code.

## Files

| File | What it is |
|---|---|
| `protocol.py` | Tiny helper that turns a raw TCP socket into "read one line, send one line" — handles the fact that TCP is a byte stream, not a message stream. |
| `kvserver.py` | Stage 1 server. A dumb in-memory map behind a TCP listener. Knows nothing about proxies or other copies of itself. |
| `proxy.py` | Stages 2–5 and the bonus. Everything about broadcasting, health-checking, catch-up, and majority voting lives here — the backends stay dumb. |
| `client.py` | Small CLI so you don't have to hand-type `nc` sessions (interactive or `--cmd` one-shot). |
| `test_kvstore.py` | End-to-end tests. Spins up real subprocesses and real sockets, no mocks. `python3 test_kvstore.py`. |
| `FLOW.md` | Sequence diagrams for each kind of request (write, read, health check, catch-up, majority vote). |
| `IMPLEMENTATION.md` | Deeper dive: concurrency model, locking, data structures, error taxonomy. |
| `WORKFLOW.md` | Runbook — exact commands to bring the cluster up, kill/restart/corrupt a copy by hand, and watch it recover. |

## Quick start

Requires only Python 3.9+ (standard library — no `pip install` needed).

```bash
# Terminal 1-3: three backend copies
python3 kvserver.py --port 7101
python3 kvserver.py --port 7102
python3 kvserver.py --port 7103

# Terminal 4: the proxy in front of them
python3 proxy.py --port 7000 --backends 127.0.0.1:7101,127.0.0.1:7102,127.0.0.1:7103

# Terminal 5: talk to it
python3 client.py --port 7000
> SET user:42 alice
OK
> GET user:42
VALUE alice
```

or with plain `nc 127.0.0.1 7000`, since the protocol is just newline-terminated
text either way. Full startup/shutdown/failure-injection instructions are in
[`WORKFLOW.md`](WORKFLOW.md).

Run the automated tests:

```bash
python3 test_kvstore.py
```

```
14 passed, 0 failed
```

## Protocol

Same command set at every hop — talking to `kvserver.py` directly and
talking to it through `proxy.py` look identical to the client.

| Client sends | Server replies | If it doesn't exist |
|---|---|---|
| `SET <key> <value>` | `OK` | — |
| `GET <key>` | `VALUE <value>` | `NOT_FOUND` |
| `DEL <key>` | `OK` | `NOT_FOUND` |
| `PING` | `PONG` | — |
| anything else | `ERR bad_command` (connection stays open) | |

Keys have no spaces; a value is everything after the first space following
the key, so values may contain spaces. Commands are one per line, ending in
`\n`.

**Proxy-only replies** (things a lone `kvserver.py` never says):

| Reply | Means |
|---|---|
| `ERR backend_unavailable` | No backend is currently reachable to answer this at all. |
| `ERR write_unavailable` | Fewer than two backends are up, so the write was refused outright (Stage 3 rule). |
| `ERR no_majority` | Stage 5 only: all up copies gave different answers, so nothing was trusted. |
| `INFO backends=<n> up=<n> read_ready=<n> read_mode=<roundrobin\|majority>` | Proxy's own status (not forwarded from a backend). |

**Admin commands** (`kvserver.py` only, used by the proxy internally, and
by a human directly for Stage 4/5 testing):

| Command | Reply | Used for |
|---|---|---|
| `INFO` | `INFO <uptime_seconds> <key_count>` | Stage 4: finding the longest-running copy to catch up from. |
| `DUMP` | `DUMP <json of the whole map>` | Stage 4: pulling a full snapshot onto a recovering copy. |
| `LOAD <key> <value>` | `LOADED` or `SKIPPED` | Stage 4 only: set-**if-absent**, so replaying a snapshot never clobbers a live write. See [`IMPLEMENTATION.md`](IMPLEMENTATION.md) for why this matters. |
| `CORRUPT <key> <value>` | `OK` | Stage 5 testing: same effect as `SET`, sent straight to one copy's own port to manufacture disagreement, per the brief. |

## What's implemented, per stage

**Stage 1 — KV over a socket.** ✅ `kvserver.py`. Thread per connection,
per-connection read buffer that accumulates bytes and peels off complete
`\n`-terminated lines (a command can arrive in pieces — see Plate 1's `"GE"`
/ `"T user:42\n"` example, which is covered by an actual test). The map
itself is one `dict` behind one `RLock`.

**Stage 2 — Proxy in front.** ✅ `proxy.py --backends host:port` (single
address). Fully transparent both directions; a dead backend produces
`ERR backend_unavailable` rather than a hang (bounded by `--op-timeout`,
default 1s).

**Stage 3 — Broadcast to three.** ✅ `proxy.py --backends h1,h2,h3`. `SET`/`DEL`
fan out to every backend currently believed up, each on its own thread, and
the proxy waits for all of them (not one after another). A write is refused
up front with `ERR write_unavailable` if fewer than two backends are up.
`GET` round-robins across the up backends. Liveness is tracked by a
background health-check loop (`PING` on a timer, default every 1s) *and* by
any write/read that fails immediately marking that backend down — both
signals feed the same up/down belief.

**Stage 4 — Catch-up (stretch).** ✅ On by default whenever there are 2+
backends. When health-checking notices a backend flip from down to up, it's
immediately made write-eligible (so it stops falling further behind) but
kept **out of the read rotation** until a background task: asks `INFO` on
every other ready backend, picks the one with the highest uptime (ties
broken by name for determinism), pulls its full state with `DUMP`, and
replays it onto the recovering backend with `LOAD` — which only sets a key
if it's *absent*, so a live write that already reached the recovering
backend during the copy is never overwritten by the (older) snapshot. Only
once that's done does it rejoin the read rotation.

**Stage 5 — Majority read (stretch).** ✅ `proxy.py --majority-read`. `GET`
queries every ready backend concurrently, groups the answers, and returns
whichever value ≥2 of them agree on — repairing (`SET`/`DEL`) any backend
that disagreed, and logging it. All-three-disagree returns
`ERR no_majority`.

**Bonus — Quorum writes.** ✅ `proxy.py --quorum-write`. Acknowledges a write
once a majority of the backends it was sent to have confirmed, instead of
waiting for all of them; the straggler is still sent, just not waited on.

**Not implemented:** per-key version numbers (see trade-offs below); queued
writes for a down copy (Stage 4's DUMP/LOAD catch-up was chosen instead —
see below); the chaos-script bonus.

## Decisions made where the brief was vague

- **Health-check strategy:** both a timer (`PING` every `--health-interval`
  seconds, default 1s) *and* opportunistic detection (a write or read that
  fails is treated as down immediately, not on the next tick). The timer
  alone would leave a window where the proxy keeps trying a backend that
  just died; opportunistic-only would never notice a backend that's silently
  hung with no traffic to it.
- **Round-robin implementation:** a single shared counter, incremented and
  taken modulo the current up-count on every read, exactly per the hint.
- **Error naming:** `ERR backend_unavailable` for "nothing is reachable to
  answer this at all" (used identically in Stage 2 and whenever zero
  backends are up in Stage 3+), and a distinct `ERR write_unavailable`
  specifically for "reachable, but the two-copy rule says no" — so a client
  can tell "the whole thing is down" apart from "your write was refused by
  policy."
- **Catch-up source ("oldest running copy"):** *is* oldest actually best?
  Uptime is a proxy for "most likely to have the fewest gaps," but it's not
  perfect — a copy that's been up longest could still be missing writes if
  it was ever partitioned from the proxy without fully disconnecting. **Key
  count** would be a reasonable alternative pick (directly measures "has the
  most data" rather than inferring it from time), but two copies can
  legitimately have different key counts through no one's fault (deletes),
  so it's not strictly better — it's a different heuristic with its own
  failure mode. Uptime is what the brief asks for and is simpler to reason
  about, so that's the default; `INFO` already returns both numbers if you
  wanted to switch the tie-break.
- **"Did the catch-up work" check:** compares key counts on both sides after
  the copy (source count vs. target count) and logs it. The brief's
  suggested checksum-over-sorted-contents is a strictly better check (it
  catches value-level corruption, not just missing keys) and would be a
  small addition — noted in "what I'd do next."
- **Quorum-write's dropped-write risk:** if the un-waited-for backend's
  write genuinely fails (not just slow), that backend is now silently
  missing a key while still marked "up" — no crash, no health-check signal.
  It only gets fixed by Stage 5's read-repair (if enabled) or the next time
  that backend happens to restart. This is the trade documented in the
  brief as something to be ready to explain, so: the trade is durability
  breadth for latency, and the safety net is read-repair, not the writer.
- **Majority-read triples read traffic** (every `GET` now hits every up
  backend instead of one) — worth leaving on permanently only if your read
  volume can afford ~3x backend load in exchange for catching silent
  corruption on every read rather than only when someone happens to read a
  corrupted key through a lucky round-robin draw. I'd default it off and
  enable it for specific keys/paths that need the extra integrity check,
  not globally.
- **Corrupt vs. behind, un-tellable-apart from the value alone:** exactly as
  the hint warns — a copy that disagrees because it missed a write (behind)
  looks identical, from the proxy's point of view, to one that disagrees
  because it was directly corrupted. Both currently get the same treatment
  (outvoted and overwritten with the majority value). A per-key version
  number is the real fix and is called out explicitly as not implemented
  (see below) — with one, a "behind" copy could be recognized by a merely
  stale version and caught up via Stage 4's mechanism instead of being
  blindly overwritten, while a copy with a *current* version but wrong value
  is unambiguously corrupt.
- **Command line parsing:** a key is defined as "no spaces," so every
  command is parsed with a bounded split (`line.split(" ", 2)` style) that
  keeps the value's internal spaces intact rather than splitting on every
  space in the line — this exact bug (over-splitting and truncating a
  value/payload) bit me once during development on the leader/follower
  prototype I discarded; see `IMPLEMENTATION.md` for the full postmortem,
  it's a real trap worth knowing about.

## Known limitations

- Two backends legitimately racing to answer a majority-read's tiebreak in
  the exact same instant a repair write lands could, in principle, see one
  more inconsistent read before settling — not something the tests exercise
  under real concurrent write load, only under sequential scenarios.
- No queueing of writes for a currently-down copy (Stage 4 catches a
  recovered copy up from a peer's snapshot instead, which was the
  implemented alternative per the brief's own bonus list — trading "the down
  copy misses nothing" for "much simpler, no per-backend queue to bound or
  persist").
- No authentication, TLS, or persistence — explicitly out of scope per the
  brief.

## Terminal transcripts (real output)

Every transcript below is the actual output of running the real code in
this repo, not hand-written.

### Stage 1 — `kvserver.py` alone, plain `nc`

```
$ nc 127.0.0.1 7101
SET user:42 alice
OK
GET user:42
VALUE alice
SET user:42 alice smith
OK
GET nope
NOT_FOUND
FOO bar
ERR bad_command
PING
PONG
```

### Stage 2 — proxy in front of one backend, then the backend dies

```
== GET k through proxy (identical to talking to kv-1 directly) ==
> SET k v
OK
> GET k
VALUE v
== killing kv-1 ==
== GET k through proxy again ==
> GET k
ERR backend_unavailable
```

### Stage 3 — killing copies as we go

```
$ nc 127.0.0.1 7000
SET cart:9 2xbook
OK                              # all three stored it
... kill kv-2 ...
SET cart:9 3xbook
OK                              # two left, still fine
... kill kv-3 ...
SET cart:9 4xbook
ERR write_unavailable           # only one copy left, so no writes
GET cart:9
VALUE 3xbook                    # but reads still work
```

### Stage 4 — kill kv-3, write more, restart it fresh, watch it catch up

```
== seed 5 keys, then kill kv-3 ==
INFO backends=3 up=2 read_ready=2 read_mode=roundrobin

== write key6 while kv-3 is still down ==
SET key6 val6 -> OK

== restart kv-3 as a brand-new process (empty map, uptime resets to 0) ==

-- proxy's own log during this window --
[proxy] backend kv-3 appears DOWN
[proxy] backend kv-3 is back up
[proxy] catching kv-3 up from kv-1 (uptime 2.37s)
[proxy] kv-3 catch-up done: 6/6 snapshot keys applied, 6 keys now held (source had 6 at snapshot time)
[proxy] kv-3 back in the read rotation

== ask kv-3 directly for keys it never saw live ==
GET key1 -> VALUE val1
GET key6 -> VALUE val6          # written *after* kv-3 died — still present
INFO backends=3 up=3 read_ready=3 read_mode=roundrobin
```

### Stage 5 — corrupt one copy, read through the proxy, watch it get fixed

```
== SET user:42 alice ==
OK
== CORRUPT user:42 al?ce, sent straight to kv-3's own port ==
OK
== GET user:42 through the proxy (--majority-read) ==
VALUE alice                     # kv-1 and kv-2 outvote kv-3
== a moment later, asking kv-3 directly ==
VALUE alice                     # it got fixed

-- proxy log --
[proxy] repaired kv-3 for key 'user:42' (had 'VALUE al?ce', majority said 'VALUE alice')
```

## What I'd do next with another day

Per-key version numbers, first — they're the one thing that would let the
proxy tell "behind" apart from "corrupt" instead of treating both the same,
and they'd also let Stage 5's vote weight by recency instead of raw count.
After that, a checksum-based catch-up verification (sorted-contents hash,
not just key counts) would catch value-level corruption that survived a
Stage 4 copy, and a small chaos script (kill/restart/corrupt at random for a
minute against the running test cluster) would give real confidence beyond
the scripted failure points the current tests hit.
