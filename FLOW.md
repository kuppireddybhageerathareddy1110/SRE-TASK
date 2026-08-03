# Flow

Sequence diagrams for every path a request can take, plus the two
background loops (health-check and catch-up) that run independently of any
client request. Diagrams are [Mermaid](https://mermaid.js.org/); any
Markdown viewer with Mermaid support (GitHub, VS Code, etc.) renders them
directly — a plain-text description sits above each one too, so nothing is
lost if your viewer doesn't render Mermaid.

## Contents

1. [Byte stream → command (Stage 1 framing)](#1-byte-stream--command-stage-1-framing)
2. [SET / DEL — broadcast write](#2-set--del--broadcast-write)
3. [GET — round-robin read (Stage 3 default)](#3-get--round-robin-read-stage-3-default)
4. [GET — majority read + repair (Stage 5)](#4-get--majority-read--repair-stage-5)
5. [Health-check loop (background, always running)](#5-health-check-loop-background-always-running)
6. [Catch-up after a backend comes back (Stage 4)](#6-catch-up-after-a-backend-comes-back-stage-4)
7. [Live write racing a catch-up in progress](#7-live-write-racing-a-catch-up-in-progress)

---

## 1. Byte stream → command (Stage 1 framing)

TCP hands you bytes, not messages — a single `read()` can contain half a
command, one whole command, or three. Every connection (client↔server *and*
proxy↔backend) keeps its own buffer and only acts once a full `\n` shows up.

```mermaid
sequenceDiagram
    participant C as Client
    participant S as kvserver.py

    C->>S: bytes: "SET user:42 alice\n"
    S->>S: buffer = "SET user:42 alice\n"
    S->>S: "\n" found -> split into one line
    S->>S: handle("SET user:42 alice")
    S-->>C: "OK\n"

    C->>S: bytes: "GE"
    S->>S: buffer = "GE" (no "\n" yet)
    Note over S: do not reply -- incomplete command
    C->>S: bytes: "T user:42\n"
    S->>S: buffer = "GET user:42\n"
    S->>S: "\n" found -> split into one line
    S->>S: handle("GET user:42")
    S-->>C: "VALUE alice\n"
```

*Implemented in `protocol.py`'s `LineConn.read_line()`, used identically by
`kvserver.py` for client connections and by `proxy.py` for its connections
to each backend — same framing problem, same fix, in both places.*

---

## 2. SET / DEL — broadcast write

```mermaid
sequenceDiagram
    participant C as Client
    participant P as Proxy
    participant K1 as kv-1
    participant K2 as kv-2
    participant K3 as kv-3

    C->>P: SET cart:9 2xbook
    P->>P: count backends with up==True
    alt fewer than 2 up
        P-->>C: ERR write_unavailable
    else 2 or more up
        par sent concurrently, one thread per backend
            P->>K1: SET cart:9 2xbook
            and
            P->>K2: SET cart:9 2xbook
            and
            P->>K3: SET cart:9 2xbook
        end
        K1-->>P: OK
        K2-->>P: OK
        K3-->>P: OK
        Note over P: default mode waits for every backend it sent to;<br/>--quorum-write mode only waits for a majority
        P-->>C: OK
    end
```

The three `SET`s in the `par` block really do fire from three separate
threads (`proxy.py: _do_write`), not a `for` loop — a broadcast write costs
about as long as the *slowest* backend, not the *sum* of all three.

---

## 3. GET — round-robin read (Stage 3 default)

```mermaid
sequenceDiagram
    participant C as Client
    participant P as Proxy
    participant K2 as kv-2 (next in rotation)

    C->>P: GET cart:9
    P->>P: candidates = backends with read_ready==True
    alt no candidates
        P-->>C: ERR backend_unavailable
    else at least one candidate
        P->>P: pick next candidate (shared counter mod count)
        P->>K2: GET cart:9
        K2-->>P: VALUE 3xbook
        P-->>C: VALUE 3xbook
    end
```

If the chosen backend's call fails outright (not just "not found" — an
actual connection failure), the proxy marks it down and retries once
against the next candidate before giving up, rather than failing the whole
read because of one stale rotation pick.

---

## 4. GET — majority read + repair (Stage 5)

```mermaid
sequenceDiagram
    participant C as Client
    participant P as Proxy
    participant K1 as kv-1
    participant K2 as kv-2
    participant K3 as kv-3 (corrupted)

    C->>P: GET user:42
    par queried concurrently
        P->>K1: GET user:42
        and
        P->>K2: GET user:42
        and
        P->>K3: GET user:42
    end
    K1-->>P: VALUE alice
    K2-->>P: VALUE alice
    K3-->>P: VALUE al?ce
    P->>P: group by exact answer, count each group
    Note over P: {"VALUE alice": 2, "VALUE al?ce": 1}<br/>winner = "VALUE alice" (2 >= majority)
    P-->>C: VALUE alice
    P->>K3: SET user:42 alice
    Note over P: logged: "repaired kv-3 for key 'user:42'..."
    K3-->>P: OK
```

If every backend disagrees (no group reaches 2), the proxy returns
`ERR no_majority` instead of guessing, and repairs nothing (there's no
majority to repair *toward*).

---

## 5. Health-check loop (background, always running)

Independent of any client request — one loop per proxy process, ticking
every `--health-interval` seconds (default 1s).

```mermaid
sequenceDiagram
    participant P as Proxy (health-check loop)
    participant K as some backend

    loop every health-interval seconds
        P->>K: PING
        alt PONG within health-timeout
            K-->>P: PONG
            alt was already up
                P->>P: up = true (no change)
            else was down
                P->>P: up = true
                Note over P: transition detected -> kick off Stage 4 catch-up<br/>(see diagram 6), unless this is the very first<br/>check any backend has ever had (cold start:<br/>nothing to catch up from, mark read_ready directly)
            end
        else no reply / timeout / connection refused
            K--xP: (nothing)
            P->>P: up = false, read_ready = false
        end
    end
```

A write or read that fails on the spot marks a backend down immediately too
(see diagrams 2 and 3) — the timer isn't the *only* way a failure is
noticed, just the way a *silent* failure (nothing currently talking to that
backend) eventually gets noticed.

---

## 6. Catch-up after a backend comes back (Stage 4)

Triggered by the health-check loop's down→up transition (diagram 5), runs
on its own background thread so it doesn't block the health-check loop from
checking everyone else.

```mermaid
sequenceDiagram
    participant P as Proxy
    participant K3 as kv-3 (just restarted, empty map)
    participant K1 as kv-1 (oldest survivor)

    Note over K3: health check just marked kv-3 up=true<br/>but read_ready is still false
    P->>P: candidates = other backends with read_ready==true
    par ask every candidate its uptime
        P->>K1: INFO
        K1-->>P: INFO 187.42 6
    end
    P->>P: pick highest uptime (ties broken by name) -> kv-1
    P->>K1: DUMP
    K1-->>P: DUMP {"cart:9":"2xbook", ...all 6 keys...}
    loop for every key in the snapshot
        P->>K3: LOAD <key> <value>
        alt key already present on kv-3
            K3-->>P: SKIPPED
        else key was missing
            K3-->>P: LOADED
        end
    end
    P->>K3: DUMP  (post-copy check)
    K3-->>P: DUMP {...}
    P->>P: log source count vs. target count
    P->>P: kv-3.read_ready = true
    Note over P: kv-3 rejoins the round-robin / majority-read pool
```

---

## 7. Live write racing a catch-up in progress

This is the wrinkle the brief calls out explicitly on Plate 4 ("writes are
still arriving during all this"). The fix is `LOAD`'s set-if-absent
semantics plus the *order* in which kv-3 is made write-eligible vs.
read-eligible.

```mermaid
sequenceDiagram
    participant P as Proxy
    participant K3 as kv-3 (recovering)
    participant K1 as kv-1 (snapshot source)
    participant C as some other client

    Note over P,K3: kv-3.up is set true THE INSTANT it's seen alive --<br/>before catch-up even starts -- so it's already<br/>eligible to receive broadcast writes
    P->>K3: (still catching up: read_ready=false, up=true)

    C->>P: SET shared updated
    par broadcast reaches kv-3 too, because up==true already
        P->>K3: SET shared updated
    end
    K3-->>P: OK
    Note over K3: kv-3 now holds shared=updated, live,<br/>*before* the snapshot below even arrives

    P->>K1: DUMP
    K1-->>P: DUMP {"shared":"original", ...}
    Note over K1: this snapshot is from BEFORE the live write above,<br/>so it still says shared=original -- stale
    P->>K3: LOAD shared original
    K3-->>P: SKIPPED
    Note over K3: key already present (from the live write) --<br/>LOAD refuses to overwrite it. "original" never<br/>clobbers "updated".

    P->>K3: (all other, non-conflicting keys) LOAD ...
    K3-->>P: LOADED (for each)
    P->>P: kv-3.read_ready = true
```

The key mechanism: **`LOAD` is set-if-absent, never overwrite.** Any key a
live write already delivered to the recovering backend wins automatically,
because the snapshot replay simply skips it. The only way this could still
lose a write is if the *live write itself* fails to reach kv-3 for some
unrelated reason (e.g. it was mid-connect at that exact instant) — in that
narrow case the snapshot's older value would apply instead, which is the
one accepted gap in an otherwise small, dependency-free design (see
`README.md`'s "Known limitations").
