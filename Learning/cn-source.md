# Computer Networks (CN) — In-Depth Learning Resources

> Part of a systems/backend/DevOps learning track. Pairs tightly with `socket-source.md` — consider studying them side by side rather than one after the other.

## Why Computer Networks

Whether you're debugging "why can't this pod reach that service," writing a socket server, or figuring out why a TLS handshake is failing, you're relying on CN fundamentals. This is the theory that makes `socket-source.md` and a good chunk of `kubernetes-source.md`'s networking section click.

## Prerequisites

- Basic Linux command line (`ping`, `curl`, `dig`)
- Helpful in parallel: `socket-source.md` — theory and code reinforce each other

## Phase 1 — Foundational Text

- **"Computer Networking: A Top-Down Approach" by Kurose & Ross, 9th Edition (published 2025)** — the standard networking textbook worldwide, working from the application layer down to the physical layer, which keeps things concrete and motivated rather than abstract. The official companion site — https://gaia.cs.umass.edu/kurose_ross/ — has free slides and the classic **Wireshark labs**, useful even if you don't own the book. The 9th edition added updated coverage of Wi-Fi 6, 5G, HTTP/3, and QUIC.
- **Free-first alternative**: **"High Performance Browser Networking" by Ilya Grigorik** — completely free at https://hpbn.co — more applied and web-focused: TCP, TLS, HTTP/1.1 through HTTP/3, WebSocket, WebRTC. A great complement even if you do get the Kurose & Ross book.

## Phase 2 — Build It Yourself (the best way to actually learn TCP)

- **Stanford CS144** — https://cs144.github.io — the paid, instructor-led version runs through Stanford Online, but the self-paced course materials and lab checkpoints are freely available on GitHub. The centerpiece project has you **build your own reliable TCP implementation from scratch** on top of raw UDP/IP — sequence numbers, ACKs, retransmission, flow control, congestion control. This is genuinely one of the best hands-on projects in computer science education for making TCP concrete instead of abstract.
- **Wireshark practice**: install Wireshark, capture your own traffic, and follow along with the Kurose & Ross chapters — watch a real TCP handshake, a real DNS lookup, a real HTTP request happen on your own machine.

## Phase 3 — Broader Practical Networking

- Subnetting & IP addressing drills (plenty of free subnetting calculators and quiz sites)
- DNS deep dive: recursive vs. authoritative resolution, record types (A, AAAA, CNAME, MX, TXT)
- If you want more of a network-engineer (routers/switches) angle rather than a pure CS angle, Cisco's **Networking Academy** offers free introductory courses.

## Core Topics Checklist

- [ ] Layered models: OSI vs. TCP/IP
- [ ] Application layer: HTTP/1.1, HTTP/2, HTTP/3, DNS
- [ ] Transport layer: TCP (handshake, flow control, congestion control, retransmission) vs. UDP
- [ ] Network layer: IP addressing, subnetting, routing basics
- [ ] Link layer: Ethernet, ARP, switching basics
- [ ] TLS/SSL basics: handshake, certificates, why HTTPS is trusted
- [ ] NAT — and specifically how it affects container/Kubernetes networking
- [ ] Packet analysis with Wireshark/tcpdump

## Next Step

Once you've covered the transport-layer chapters, start (or continue) `socket-source.md` in parallel — writing the code is what makes the theory permanent. The CN projects in `target-project.md` (especially the CS144 TCP-from-scratch project) are the strongest way to cement this material.
