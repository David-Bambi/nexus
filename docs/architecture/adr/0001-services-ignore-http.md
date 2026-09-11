---
status: accepted
date: 2026-09-11
---

# 0001 — Services ignore HTTP

## Status

Accepted

## Decision

All business rules live in a `services/` layer. This layer never imports
Flask or anything request/session/template related. It exposes plain
Python functions that take simple arguments and return domain objects or
raise domain exceptions.

Flask routes are adapters only: validate input, call a service, render a
template. No business rule in a route. No direct database access from a
template.

## Why

V2 adds a CLI, V3 or V4 agentic capabilities. Both will call the exact same
service functions. It becomes structurally impossible for an agent to
bypass a rule the browser respects. Without this separation, every new
interface duplicates the logic and the rules drift apart.

## Compliance check

`grep -r "flask" src/services/` returns nothing. An automated test
(`tests/test_architecture.py`) enforces this.
