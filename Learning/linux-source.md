# Linux — In-Depth Learning Resources

> Part of a systems/backend/DevOps learning track. See `README.md` for how this fits with the other files, and `target-project.md` for hands-on projects once you've worked through this one.

## Why Linux

Linux runs the overwhelming majority of servers, cloud infrastructure, Docker hosts, and Kubernetes nodes. Nearly every other file in this collection (Docker, Kubernetes, Sockets, OS internals) assumes you're comfortable on a Linux command line. It's the single highest-leverage topic in this whole roadmap.

## Prerequisites

- None, technically — just willingness to spend real time in a terminal.
- A machine to practice on: a real install, a VM, WSL2 (Windows), or a free cloud VM. The browser-based options below let you start with zero setup.

## Phase 0 — Get an Environment

Pick one:
- **Dual-boot / VM**: install Ubuntu or Debian in VirtualBox/VMware, or dual-boot your machine.
- **WSL2** (Windows users): fastest way to get a real Linux shell without leaving Windows.
- **Cloud VM**: free tiers from Oracle Cloud or AWS, or a $4–6/month VPS (DigitalOcean, Hetzner) — closer to how you'll use Linux professionally.
- **No install yet**: start with the browser-based platforms under Practice below, then move to a real machine.

## Phase 1 — Command-Line Fundamentals (roughly weeks 1–2)

1. **Linux Journey** — https://labex.io/linuxjourney — (the original linuxjourney.com now redirects here; it's still free and actively maintained, just under new stewardship). A structured, beginner-friendly path: what Linux is, command-line basics, text manipulation, permissions, processes, package management, the boot process.
2. **"The Linux Command Line" by William Shotts** — free PDF at linuxcommand.org — a genuinely complete book that goes further into scripting than most free resources.
3. **MIT Missing Semester** — https://missing.csail.mit.edu/ — do "Course Overview + the Shell" and "Shell Tools and Scripting" now; save the Git/Vim/debugging lectures for later or for `additional-topics-source.md`.
4. **Practice immediately, don't wait**: OverTheWire **Bandit** — https://overthewire.org/wargames/bandit/ — 33 levels, SSH into a real box and solve command-line puzzles. Run this in parallel with the above.

## Phase 2 — System Administration (roughly weeks 3–5)

Core topics to build real competence in:
- Users, groups, permissions (`chmod`, `chown`, `umask`), `sudo`
- Process management (`ps`, `top`/`htop`, `kill`, job control)
- Package management (`apt`/`dnf`/`pacman`)
- The Filesystem Hierarchy Standard (FHS) and mounting
- `systemd`/`systemctl` — starting, stopping, enabling services
- Basic networking commands: `ip`, `ss`, `curl`, `dig`/`nslookup`
- Text processing: `grep`, `sed`, `awk`, `cut`, `sort`, `uniq`, pipes
- Log management: `journalctl`, `/var/log`, log rotation
- Cron and systemd timers for scheduled tasks

Resources:
- **Arch Wiki** — https://wiki.archlinux.org — the best single reference on the internet for almost any Linux topic, regardless of which distro you actually run.
- **"How Linux Works" by Brian Ward** (No Starch Press) — builds a real mental model of the boot process, devices, and administration instead of just listing commands to memorize.
- **explainshell.com** — paste any command and get every flag broken down; useful while you're still building fluency.

## Phase 3 — Advanced / Internals (week 6 onward)

- **"The Linux Programming Interface" by Michael Kerrisk** (No Starch Press) — the definitive reference for Linux system programming: syscalls, file I/O, processes, signals, threads, IPC. Dense but unmatched, and the natural bridge into both `os-source.md` and `socket-source.md`.
- **Linux From Scratch** — https://www.linuxfromscratch.org — build an entire working Linux system from source, package by package. One of the best ways to truly understand how a distro fits together.
- Skim the **Linux kernel source** (kernel.org) once you're comfortable — you don't need to read it deeply yet, just confirm to yourself it isn't magic.

## Hands-on Practice Platforms

| Platform | What it's for | Cost |
|---|---|---|
| OverTheWire Bandit | Command-line fundamentals, SSH-based | Free |
| killercoda.com | Browser-based Linux + Kubernetes scenarios, no install | Free |
| LabEx (labex.io) | Interactive labs; also hosts the current Linux Journey | Free tier |
| Your own VM/VPS | Real-world admin practice | Free–$6/mo |

## Core Topics Checklist

- [ ] Filesystem hierarchy & navigation
- [ ] File permissions & ownership (chmod, chown, umask, ACLs)
- [ ] Process management & signals
- [ ] Package management (apt/yum/dnf/pacman)
- [ ] Shell scripting (bash: variables, loops, conditionals, functions)
- [ ] Text processing (grep, sed, awk, cut, sort, uniq)
- [ ] systemd & service management
- [ ] Networking basics (ip/ss/curl/dig, /etc/hosts, DNS resolution)
- [ ] Users, groups, sudo, basic PAM concepts
- [ ] Disk & storage (mount, fdisk/lsblk, basic LVM)
- [ ] Logging (journalctl, syslog, log rotation)
- [ ] Cron & systemd timers
- [ ] SSH & key-based authentication
- [ ] Environment variables & shell config (.bashrc, PATH)
- [ ] Basic hardening (ufw/firewalld, fail2ban concept, disabling root SSH login)

## Communities

- r/linuxquestions, r/linux4noobs
- Unix & Linux Stack Exchange
- Arch Wiki talk pages and forums

## Next Step

Once Phases 1–2 feel solid, start the **Linux projects** in `target-project.md` — don't wait until you've "finished" Linux, since there's always more depth available. It's also worth starting `os-source.md` in parallel now, since OS theory and Linux administration reinforce each other heavily.
