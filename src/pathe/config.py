"""Defaults, overridable from the environment."""

import os

# The four cinemas actually in reach. Everything defaults to these rather than
# to all 31: a national sweep is ~1000 requests and answers a question nobody
# asked. Override with PATHE_CINEMAS as a comma-separated list of slugs.
DEFAULT_CINEMAS = [
    "pathe-helmond",
    "pathe-eindhoven",
    "pathe-tilburg-centrum",
    "pathe-tilburg-stappegoor",
]

# Pathé publishes ~10 months out, but that tail is almost entirely opera and
# ballet encores. Two months covers the real programme; `--days` widens it when
# you are chasing something like an André Rieu date.
DEFAULT_HORIZON_DAYS = 60


def default_cinemas():
    raw = os.environ.get("PATHE_CINEMAS", "").strip()
    if not raw:
        return list(DEFAULT_CINEMAS)
    return [s.strip() for s in raw.split(",") if s.strip()]


def resolve(requested, known_slugs):
    """Map what the user typed onto real cinema slugs.

    Resolved against the live list rather than by string surgery, because the
    prefix is not universal -- `pathe-helmond` has it, `koninklijk-theater-
    tuschinski` does not -- so guessing gets Tuschinski wrong. Accepts the exact
    slug, the slug without `pathe-`, or a unique case-insensitive substring.
    """
    known = list(known_slugs)
    out, unknown = [], []
    for raw in requested:
        needle = raw.strip().lower().replace(" ", "-")
        if not needle:
            continue
        if needle in known:
            out.append(needle)
            continue
        if f"pathe-{needle}" in known:
            out.append(f"pathe-{needle}")
            continue
        hits = [s for s in known if needle in s]
        if len(hits) == 1:
            out.append(hits[0])
        else:
            unknown.append(raw)
    return list(dict.fromkeys(out)), unknown
