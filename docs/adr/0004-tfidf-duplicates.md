# ADR 0004: Duplicate detection with TF-IDF instead of an ML service

- Status: Accepted
- Date: 2026-10-30

## Context
Repeated questions split votes across near-identical cards. Suggesting existing questions while
someone types fixes that at the source, but it runs on every few keystrokes for every participant.

## Decision
A small TF-IDF and cosine-similarity implementation in pure Python, over the session's own
questions, with stopword removal and light stemming. Words that are rare in the session count for
more than common ones.

## Consequences
- No external service, API key, cost or latency, and the results are explainable.
- It matches shared vocabulary, not meaning: "DB" and "database" do not match. An embedding model
  could replace `find_similar` behind the same signature if that becomes worth its cost.
