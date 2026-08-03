# Docker — In-Depth Learning Resources

> Part of a systems/backend/DevOps learning track. Builds directly on `linux-source.md` (namespaces/cgroups) and leads into `kubernetes-source.md`.

## Why Docker

Docker is the de facto standard for packaging and shipping software consistently across environments, and it's the foundation Kubernetes builds on. Nearly every modern deployment pipeline touches it somewhere.

## Prerequisites

- Basic Linux command line
- Helpful, not required: a first pass through `os-source.md`'s process/memory basics — Docker is, under the hood, mostly Linux namespaces + cgroups with excellent UX on top

## Phase 1 — Fundamentals (week 1)

- **Official docs, Get Started** — https://docs.docker.com/get-started/ — genuinely well-written and kept current; start here before any third-party tutorial.
- **freeCodeCamp's Docker Full Course** — on the freeCodeCamp YouTube channel (also written up at freecodecamp.org/news/docker-full-course/) — a current, job-ready-oriented full course covering Dockerfiles through image management.
- **The Docker Handbook** — freecodecamp.org/news/the-docker-handbook/ — free, well-organized written reference to pair with video learning.

## Phase 2 — Core Skills (weeks 2–3)

- Dockerfile instructions, layer caching, multi-stage builds (docs.docker.com reference section)
- Docker Compose for multi-container apps (docs.docker.com/compose)
- Image registries: Docker Hub, tagging conventions, private registries
- Docker networking: bridge vs host vs overlay — connects directly to `cn-source.md`
- Volumes and bind mounts for persistent data

## Phase 3 — Depth / Production (week 4+)

- **"Docker Deep Dive" by Nigel Poulton** — a well-regarded, regularly updated book covering image layers, storage drivers, Swarm, and security in more depth than the docs alone.
- Docker security basics: running as non-root, minimal base images, image scanning.
- **Understand what Docker is actually built on**: Linux namespaces and cgroups. This is the single best thing you can do to stop treating Docker as a black box. Liz Rice's "Containers From Scratch" conference talk (search it on YouTube) is the classic walkthrough of building a minimal container yourself with just `chroot`, namespaces, and cgroups — no Docker involved.

## Hands-on Practice

> **Heads up**: the classic zero-install browser sandbox **Play with Docker** was deprecated and shut down starting March 1, 2026. You'll still see it referenced in a lot of older tutorials, but it's gone now — don't chase that link. Use one of these instead:
- **Docker Desktop**, installed locally (free for personal use / small business) — the standard path for most learners.
- **LabEx's Docker Playground** — https://labex.io — browser-based, no install, positioned as the direct successor to Play with Docker.
- **killercoda.com** — also has Docker scenarios alongside its Kubernetes ones.

## Core Topics Checklist

- [ ] Images vs containers vs registries
- [ ] Dockerfile instructions, caching, multi-stage builds
- [ ] Docker Compose for multi-service apps
- [ ] Networking modes (bridge/host/none/overlay)
- [ ] Volumes & bind mounts
- [ ] Resource limits (CPU/memory)
- [ ] Security basics (non-root user, minimal images, scanning)
- [ ] Namespaces & cgroups — the Linux mechanisms Docker is built on
- [ ] Docker Swarm basics (mostly superseded by Kubernetes, but useful context for *why* Kubernetes won out)

## Next Step

Containerize something you've already built — see the Docker section of `target-project.md` — before moving on to `kubernetes-source.md`. Kubernetes assumes solid Docker fundamentals, so don't skip ahead.
