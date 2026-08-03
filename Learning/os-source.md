# Operating Systems — In-Depth Learning Resources

> Part of a systems/backend/DevOps learning track. Arguably the most foundational file in the whole set — processes, memory, and concurrency underlie Linux administration, Docker's namespaces/cgroups, and socket I/O models.

## Why Operating Systems

You can use Linux, Docker, and sockets without ever formally studying OS internals — but understanding *why* they work the way they do (processes vs. threads, virtual memory, scheduling, filesystems) is what turns "I can run these commands" into "I can reason about and debug systems I've never seen before."

## Prerequisites

- C programming basics (or willingness to pick it up alongside — the classic OS teaching materials are all in C)
- Comfort with the Linux command line

## Phase 1 — The Core Text

- **"Operating Systems: Three Easy Pieces" (OSTEP)** — https://pages.cs.wisc.edu/~remzi/OSTEP/ — completely free, extremely well-regarded, organized around three themes: Virtualization (CPU & memory), Concurrency, and Persistence (file systems). Use this as your spine resource for the whole topic — it's free, actively maintained (version 1.10+), and better-written than most paid textbooks covering the same ground.
- Optional second reference: **"Operating System Concepts"** (the "Dinosaur Book") by Silberschatz, Galvin & Gagne — more traditional/academic; useful for a different angle on the same material, not required if OSTEP already clicks for you.

## Phase 2 — Hands-on Kernel-Level Practice

- **MIT 6.1810, "Operating System Engineering"** (formerly numbered 6.S081 / 6.828 — same course, renumbered) — https://pdos.csail.mit.edu/6.1810/ — one of the best free OS courses in the world. You build directly on **xv6**, a small teaching Unix-like OS, through labs covering system calls, page tables, traps/interrupts, copy-on-write fork, a multithreaded kernel, and a real (if simplified) file system.
- Pair it with OSTEP: read the matching OSTEP chapter, then do the corresponding 6.1810 lab — theory and hands-on implementation reinforce each other far better than either alone.

## Phase 3 — Concurrency Deep-Dive

- OSTEP's concurrency chapters, then practice writing real pthreads code in C: mutexes, condition variables, producer/consumer.
- **"The Little Book of Semaphores" by Allen Downey** — free PDF — a great source of extra synchronization practice problems once the basics click.

## Phase 4 — Going Further (optional)

- Skim parts of **"Linux Kernel Development" by Robert Love** if you want production-kernel-level depth rather than the teaching-OS level of xv6.
- **OSDev Wiki** — https://wiki.osdev.org — if you want to go all the way and write a toy OS from a bootloader up.

## Core Topics Checklist

- [ ] Processes vs. threads
- [ ] CPU scheduling (FCFS, Round Robin, MLFQ — and why they trade off differently)
- [ ] Virtual memory & paging
- [ ] Concurrency: locks, condition variables, semaphores, deadlock
- [ ] System calls & the user/kernel boundary
- [ ] File systems (inodes, journaling)
- [ ] I/O & device drivers (conceptual level is enough for most learners)
- [ ] Interprocess communication
- [ ] Memory allocation (how `malloc` actually works)
- [ ] Namespaces & cgroups — the exact mechanisms Docker relies on (ties directly into `docker-source.md`)

## Communities

- r/osdev (mostly for the "build your own OS from scratch" crowd)
- MIT 6.1810's own course staff contact, if you're following the current term's offering

## Next Step

Do the OS-related projects in `target-project.md` — most importantly, work through as many of the MIT 6.1810 labs as you can. There's no better structured OS project sequence available for free anywhere.
