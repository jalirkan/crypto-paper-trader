"""Execution engine (OMS) — built long before it's allowed to touch money.

Design principles, in order of importance:

1. **The journal is truth, written ahead of action.** Every order is persisted
   as PENDING_NEW before the exchange ever hears about it. A crash at any
   instruction leaves a record that reconciliation can resolve.
2. **A lost acknowledgment is not a failed order.** Timeouts move orders to
   UNKNOWN, never to REJECTED. Only the exchange's own answer (queried by our
   idempotent client id) can settle what happened.
3. **Everything is idempotent.** Client ids are deterministic; fills dedupe by
   exchange trade id; reconciliation can run any number of times.
4. **When reality and the journal disagree beyond tolerance, freeze.** The
   OMS never "fixes" a position drift by trading. It halts and demands eyes.

Live trading remains gated per RESEARCH_PLAN §8: a real exchange adapter may
only be enabled after a sleeve survives ≥3 months of forward paper, with
explicit human action. Until then: MockExchange only.
"""
