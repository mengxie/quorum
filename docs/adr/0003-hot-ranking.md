# ADR 0003: A "hot" ranking for live sessions

- Status: Accepted
- Date: 2026-10-30

## Context
Sorting by votes lets the first questions win simply because they have been visible longest.
Sorting by time ignores what the room wants.

## Decision
`score = (votes + 1) / (age_in_10_minute_units + 2) ^ 1.5`, the shape of Hacker News' ranking with
the time unit scaled from hours to minutes. Ties go to the newer question. "Newest" is offered as a
second order.

## Consequences
- A fresh question with a few votes can overtake an older one with more, but a runaway favourite
  stays on top. Both behaviours are pinned by tests.
- The formula is one pure function with a policy object, so it can be tuned without touching
  anything else.
