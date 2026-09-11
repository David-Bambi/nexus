---
status: accepted
date: 2026-09-11
---

# 0004 — Localhost-only binding

## Status

Accepted

## Decision

In V1 the server listens on `127.0.0.1` exclusively. No authentication is
implemented.

## Why

Without authentication, binding on `0.0.0.0` would expose the data to the
whole local network. Server deployment is a goal for a later version and
will arrive **with** authentication, never before it.
