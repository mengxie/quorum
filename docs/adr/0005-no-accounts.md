# ADR 0005: No accounts: anonymous participants and hashed host links

- Status: Accepted
- Date: 2026-10-30

## Context
Asking a question in a talk should take seconds. Sign-up would stop most people, and anonymity
encourages the questions people are hesitant to ask out loud.

## Decision
- Participants get a random id in a signed, `SameSite=Lax` session cookie: enough for one vote per
  browser and for marking "your" questions.
- The host gets a 192-bit random link. Only its SHA-256 hash is stored and it is compared in
  constant time. It is shown once; visiting it adds the session to the host's cookie and redirects,
  so the secret leaves the address bar. `Referrer-Policy: no-referrer` stops it leaking to other sites.
- Asking is rate limited per participant.

## Consequences
- Joining takes one scan of a QR code.
- Voting integrity is per browser, which suits a room of colleagues, not a public poll.
- Losing the host link means losing host access; the interface says so when it shows the link.
