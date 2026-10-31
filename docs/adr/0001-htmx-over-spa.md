# ADR 0001: Server-rendered HTML with HTMX instead of a single-page app

- Status: Accepted
- Date: 2026-10-30

## Context
Quorum's screens are lists and forms that change when other people act. A single-page app would
need a JSON API, a client-side state store, a build pipeline and duplicated validation, for little
benefit here.

## Decision
Render HTML on the server with Jinja. Every action is a real form. HTMX upgrades forms to partial
updates and swaps in fresh HTML fragments when the server signals a change. A 40-line script adds
two conveniences (copy buttons and a character counter); nothing depends on it.

## Consequences
- One language, one place for rules and rendering, and no client build step.
- Works with JavaScript disabled, which the tests verify.
- A strict Content Security Policy is easy, because there are no inline scripts.
- Rich client-side interactions (drag and drop, offline use) would need more JavaScript.
