# ADR 0002: Real-time with Server-Sent Events and PostgreSQL LISTEN/NOTIFY

- Status: Accepted
- Date: 2026-10-30

## Context
Every open screen must update when anyone asks, votes or moderates, and the app should scale to
several instances without adding infrastructure.

## Decision
- Each screen opens a Server-Sent Events stream. Updates only flow server to client, so SSE is
  simpler than WebSockets, works through ordinary HTTP proxies and reconnects automatically.
- The stream carries only a `changed` signal; the page then fetches fresh HTML. The stream can
  therefore never reveal anything a normal request would not, and there is one rendering path.
- Changes are published with `pg_notify`. Each instance holds one `LISTEN` connection and wakes its
  own streams through an in-process hub, whose one-slot queues collapse bursts into one refresh.

## Consequences
- Multi-instance real-time with nothing but PostgreSQL. Verified by a test with two notifiers.
- Each change costs one fragment request per open screen: fine for rooms of hundreds, and the
  queues stop bursts multiplying it.
- NOTIFY is not durable; a screen that reconnects simply refetches, so nothing is lost.
