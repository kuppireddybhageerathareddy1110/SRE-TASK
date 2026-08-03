# Socket Programming — In-Depth Learning Resources

> Part of a systems/backend/DevOps learning track. Pairs especially well with `cn-source.md` (the theory) and `os-source.md` (file descriptors, I/O models). See `target-project.md` for projects.

## Why Socket Programming

Sockets are the actual API underneath almost everything networked: web servers, databases, chat apps, game servers, and the networking layers inside Docker and Kubernetes themselves. Learning sockets — ideally in C first — demystifies "how does a network connection actually work in code," which using high-level HTTP frameworks alone will never teach you.

## Prerequisites

- Comfort with C (or willingness to learn just enough alongside)
- Basic Linux command line (see `linux-source.md`)
- Helpful in parallel: basic TCP/IP concepts from `cn-source.md` — theory and code reinforce each other, so consider studying them side by side rather than strictly in sequence

## Phase 1 — Concepts Before Code

- **Beej's Guide to Networking Concepts** — https://beej.us/guide/bgnet0/ — a no-code, plain-English companion guide explaining what sockets, ports, and protocols actually are. Read this first if TCP/IP still feels abstract.
- Skim the TCP/UDP sections of `cn-source.md`'s resources in parallel.

## Phase 2 — Classic C Sockets (the real deep dive)

- **Beej's Guide to Network Programming** — https://beej.us/guide/bgnet/ — the definitive free, beginner-friendly guide to BSD/POSIX sockets in C, still maintained by its author. Type every example yourself instead of copy-pasting — the guide is written expecting that.
- **"UNIX Network Programming, Volume 1" by W. Richard Stevens** — the field's definitive, most rigorous reference. Dense — use it after Beej's, as a deeper second pass or a reference to return to.
- **"TCP/IP Sockets in C" by Donahoo & Calvert** — shorter and more classroom-friendly than Stevens; a good middle option.

## Phase 3 — Practical / Modern Languages

- **Python**: official docs at docs.python.org/3/library/socket.html, plus Real Python's socket programming tutorial — a fast way to build practical tools once the C fundamentals have clicked.
- **Go**: the `net` package (pkg.go.dev/net) — especially relevant since Docker and Kubernetes are themselves written in Go and use these exact primitives.

## Phase 4 — Beyond Basic Sockets

- **Beej's Guide to Unix IPC** — linked from beej.us/guide/ — once sockets feel natural, round out your IPC knowledge with pipes, shared memory, and semaphores.
- Learn **`select()`/`poll()`/`epoll()`** for handling many connections at once — the conceptual root of how nginx, Redis, and Node.js achieve high concurrency, and covered directly in Beej's guide.
- Read the source of a small, real socket-based server (even a toy one) to see idiomatic patterns once you've built a few yourself.

## Practice Progression

1. TCP echo server + client (single client)
2. Handle multiple clients — first with `fork()`, then threads, then refactor to `select()`/`epoll()`
3. A UDP-based tool (e.g., a simple ping-style utility)
4. A tiny application protocol layered on top of TCP (see `target-project.md` for full project ideas)

## Core Topics Checklist

- [ ] TCP vs UDP — reliability, ordering, when to use which
- [ ] `socket()`, `bind()`, `listen()`, `accept()`, `connect()`
- [ ] `send()`/`recv()`, `sendto()`/`recvfrom()`
- [ ] Blocking vs non-blocking I/O
- [ ] `select()`/`poll()`/`epoll()` for concurrent connections
- [ ] Byte order / endianness, `htons`/`ntohs`/`htonl`/`ntohl`
- [ ] Socket options (e.g., `SO_REUSEADDR`)
- [ ] Handling partial reads/writes correctly
- [ ] Designing a simple framing / length-prefixed protocol over TCP
- [ ] IPv4 vs IPv6 (`getaddrinfo()` and friends)

## Communities

- Stack Overflow (tag: sockets)
- r/C_Programming, r/networking
- Beej himself is reachable by email for guide corrections (see the guide's contact section) — a nice reminder this is still a living, maintained resource, not an abandoned relic

## Next Step

Start the socket projects in `target-project.md` the moment you finish Beej's chapters on `bind`/`listen`/`accept` — build the TCP echo server before you've even finished the whole guide. Writing code early is what makes the reading stick.
