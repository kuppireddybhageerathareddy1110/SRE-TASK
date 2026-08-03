# Kubernetes — In-Depth Learning Resources

> Part of a systems/backend/DevOps learning track. Assumes solid `docker-source.md` fundamentals first.

## Why Kubernetes

Kubernetes is the de facto standard for running containers at scale in production. It's a deep, sprawling system — the goal isn't to memorize every API object, but to understand the architecture well enough to reason about and debug real clusters.

## Prerequisites

- Solid Docker fundamentals (images, containers, networking, volumes)
- Comfortable reading/writing YAML
- Basic Linux + networking concepts

## Phase 1 — Concepts (week 1)

- **Official docs, Concepts section** — https://kubernetes.io/docs/concepts/ — start with cluster architecture and the core objects (Pods, Deployments, Services) before touching `kubectl`.
- **"Learn Kubernetes Basics"** — the official interactive, in-browser tutorial linked from kubernetes.io — zero setup needed to get a first feel for the API.

## Phase 2 — Hands-on Basics (weeks 2–3)

- **killercoda.com/kubernetes** — a free, browser-based Kubernetes playground. This isn't just a random third-party tool — it's directly recommended in Kubernetes' own official documentation as a learning environment. Use it for `kubectl`, Pods, Deployments, and Services with zero local setup.
- Once the basics click, install **kind** or **minikube** locally — both are the tools kubernetes.io itself recommends for local learning clusters — to build muscle memory outside the browser.
- **KodeKloud's free courses** — kodekloud.com/free-courses — includes hands-on Kubernetes labs; KodeKloud also periodically runs free "Learning Week" events that open its full paid catalog for a limited time.

## Phase 3 — Deep Understanding (weeks 4–6)

- **Kubernetes the Hard Way** by Kelsey Hightower — https://github.com/kelseyhightower/kubernetes-the-hard-way — genuinely one of the best learning exercises in all of DevOps. You manually bootstrap every control-plane and worker component (etcd, kube-apiserver, controller-manager, scheduler, kubelet, kube-proxy) instead of letting `kubeadm` do it for you. Free, actively maintained (49k+ GitHub stars, ongoing activity).
- **"Kubernetes: Up & Running" (3rd edition)** by Brendan Burns, Joe Beda, Kelsey Hightower & Lachlan Evenson — written by people who built Kubernetes at Google/Microsoft; the standard book-length reference.
- **KodeKloud's CKA course** (paid, with free preview labs) — structured toward the Certified Kubernetes Administrator exam; the labs are excellent even if you never sit the exam. A free companion notes repo exists at github.com/kodekloudhub/certified-kubernetes-administrator-course.

## Phase 4 — Production Topics

- Networking: CNI plugins, Services, Ingress, NetworkPolicy
- Storage: PersistentVolumes/Claims, StorageClasses
- **Helm** (the Kubernetes package manager) — helm.sh docs
- Observability: start with `kubectl logs`/`describe`/`get events`, then layer on Prometheus + Grafana (see `additional-topics-source.md`)
- Security: RBAC, Pod Security Standards, and eventually CKS-level topics if you want to go deep

## Hands-on Practice Platforms

> **Heads up**: **Play with Kubernetes** was deprecated alongside Play with Docker (shut down starting March 1, 2026) — don't rely on tutorials that point there. Use **killercoda.com** or local **kind**/**minikube** instead.

## Core Topics Checklist

- [ ] Cluster architecture: control plane vs node components
- [ ] Pods, ReplicaSets, Deployments
- [ ] Services (ClusterIP/NodePort/LoadBalancer), Ingress
- [ ] ConfigMaps & Secrets
- [ ] Namespaces & RBAC
- [ ] Volumes, PV/PVC, StorageClasses
- [ ] Scheduling, resource requests/limits, Horizontal Pod Autoscaler
- [ ] Rolling updates & rollbacks
- [ ] Helm basics
- [ ] Troubleshooting workflow (`describe`, `logs`, `exec`, `events`)
- [ ] Networking model & CNI basics

## Next Step

Deploy your Docker Compose project from `target-project.md`'s Docker section onto a local `kind`/`minikube` cluster — that's the natural first Kubernetes project. Then work through the rest of the Kubernetes projects there, including a full run of Kubernetes the Hard Way.
