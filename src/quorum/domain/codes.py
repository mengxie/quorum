"""Short join codes people can read off a slide and type on a phone."""

import secrets

# No 0/O or 1/I: nothing that can be misread from the back of the room.
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6


def new_event_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def normalise_code(raw: str) -> str | None:
    """Accepts 'k7p-4qz', 'K7P 4QZ' and similar; returns the canonical code or None."""
    code = "".join(raw.split()).replace("-", "").upper()
    if len(code) != CODE_LENGTH or any(char not in ALPHABET for char in code):
        return None
    return code


def format_code(code: str) -> str:
    """Two groups of three are easier to read aloud: K7P-4QZ."""
    return f"{code[:3]}-{code[3:]}"
