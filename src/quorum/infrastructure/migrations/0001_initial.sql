CREATE TABLE events (
    id            uuid        PRIMARY KEY,
    code          text        NOT NULL UNIQUE CHECK (code ~ '^[A-HJ-NP-Z2-9]{6}$'),
    title         text        NOT NULL CHECK (char_length(title) BETWEEN 1 AND 100),
    host_key_hash text        NOT NULL,
    is_open       boolean     NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL
);

CREATE TABLE questions (
    id          uuid        PRIMARY KEY,
    event_id    uuid        NOT NULL REFERENCES events (id) ON DELETE CASCADE,
    author_id   uuid        NOT NULL,
    author_name text        CHECK (char_length(author_name) BETWEEN 1 AND 40),
    text        text        NOT NULL CHECK (char_length(text) BETWEEN 1 AND 280),
    status      text        NOT NULL DEFAULT 'open'
                            CHECK (status IN ('open', 'answering', 'answered', 'hidden')),
    created_at  timestamptz NOT NULL
);

CREATE INDEX questions_by_event ON questions (event_id, created_at);
CREATE INDEX questions_by_author ON questions (event_id, author_id, created_at);

-- The database itself guarantees that only one question is "now answering" per event.
CREATE UNIQUE INDEX questions_one_answering ON questions (event_id) WHERE status = 'answering';

CREATE TABLE votes (
    question_id    uuid        NOT NULL REFERENCES questions (id) ON DELETE CASCADE,
    participant_id uuid        NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (question_id, participant_id)
);
