# Additional Topics Worth Studying

Linux, Sockets, Docker, Kubernetes, OS, and CN form a strong systems/backend/DevOps foundation — but they don't stand alone in a real career. Here's what most naturally rounds them out, roughly in priority order. Pick 2–3 that match your actual goal rather than trying to do all of these at once — see "How to Prioritize" at the bottom.

## 1. Git & Version Control
*You'll use this every single day, in every other project on this list.*
- **Beej's Guide to Git** — beej.us/guide/git/ (same author as the sockets guide, same clear style)
- **MIT Missing Semester**, the Git lecture — https://missing.csail.mit.edu/
- Practice: **Learn Git Branching** — learngitbranching.js.org — interactive, visual, genuinely fun

## 2. Data Structures & Algorithms
*Needed for technical interviews regardless of specialization.*
- roadmap.sh/datastructures-and-algorithms
- NeetCode or LeetCode for structured practice

## 3. System Design
*The natural next step once Docker/Kubernetes/CN feel solid — "how do you architect something at scale."*
- **The System Design Primer** — https://github.com/donnemartin/system-design-primer — free, thorough, includes sample solved problems and interview prep material
- **"Designing Data-Intensive Applications" by Martin Kleppmann** — arguably the single best book on how real distributed data systems (databases, caches, queues) actually work under the hood

## 4. Databases (SQL & NoSQL)
*Almost every real backend system needs one.*
- Official PostgreSQL tutorial (postgresql.org/docs)
- Redis docs, for caching/NoSQL fundamentals
- "Designing Data-Intensive Applications" again — it's that good for this too

## 5. Distributed Systems
*The natural continuation of OS + CN once both feel solid.*
- **MIT 6.5840, "Distributed Systems"** (formerly numbered 6.824 — same course, renumbered) — https://pdos.csail.mit.edu/6.824/ — build MapReduce, then a Raft-based fault-tolerant key/value store, then a sharded database, in Go. A legendary course; free, with all materials and lab code hosted directly, no signup required.

## 6. Cloud Platforms (AWS / GCP / Azure)
*Where most of this infrastructure actually runs in industry.*
- AWS Free Tier + AWS Skill Builder's free course catalog
- roadmap.sh/devops for how cloud fits into the broader picture

## 7. CI/CD
*Automating build/test/deploy — the glue between Docker/Kubernetes and daily engineering work.*
- GitHub Actions official docs — the most practical starting point since it's free and integrated with GitHub
- roadmap.sh/devops also covers Jenkins, GitLab CI, and others

## 8. Observability & Monitoring
*Once something's deployed, you need to know if it's actually healthy.*
- Prometheus + Grafana official "Getting Started" guides
- **Google's SRE Book** — free online at sre.google/books/ — where a lot of modern monitoring/on-call philosophy originates

## 9. Infrastructure as Code
*Managing cloud/Kubernetes resources declaratively instead of by hand.*
- Terraform's official tutorials at developer.hashicorp.com/terraform/tutorials

## 10. Message Queues / Event Streaming
*How large systems decouple services from each other.*
- Apache Kafka's official quickstart (kafka.apache.org)
- RabbitMQ's official tutorials

## 11. Go (as a systems programming language)
*Docker and Kubernetes are both written in Go — learning it deepens your understanding of both, and it's the default language across cloud-native/DevOps tooling.*
- **A Tour of Go** — go.dev/tour
- "Learn Go with Tests" — free, GitHub-hosted book

## 12. Security Fundamentals
*Relevant the moment anything you build is reachable from the internet.*
- Continue past OverTheWire Bandit into **Natas** (web) and **Narnia** (binary exploitation) on the same site, if it interests you
- OWASP Top 10 — owasp.org — the standard reference for common web vulnerabilities

## 13. gRPC & Modern RPC
*Increasingly the default for service-to-service communication in exactly the stack you're building (Docker/Kubernetes-based microservices).*
- Official docs and tutorials at grpc.io

## How to Prioritize

- Goal leans **backend engineering** → Git → DSA → System Design → Databases → Go
- Goal leans **DevOps/SRE** → Git → CI/CD → Cloud → IaC → Observability
- Goal leans **deep systems/infra** → Distributed Systems → Go → Security

## Next Step

Whatever you pick, check `target-project.md` — several of the project ideas there deliberately pull in two or three of these additional topics alongside the six core ones.
