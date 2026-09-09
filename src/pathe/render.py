"""Markdown rendering.

Every command renders through the helpers here, so a film looks identical no
matter which one produced it, and the same query twice produces byte-identical
output you can paste somewhere without it drifting between runs.
"""

import datetime as dt

DAYS = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
MONTHS = [
    "januari", "februari", "maart", "april", "mei", "juni",
    "juli", "augustus", "september", "oktober", "november", "december",
]

SEP = " · "
NO_FORMAT = "—"  # a plain 2D digital screening


def dutch_date(iso):
    """`2026-09-13` -> `zondag 13 september 2026`. Weekday matters here: the
    In the Picture strand is a Sunday/Monday pattern and Pride Night is a
    Wednesday, so a bare date hides the thing you are looking for."""
    try:
        day = dt.date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso
    return f"{DAYS[day.weekday()]} {day.day} {MONTHS[day.month - 1]} {day.year}"


def film_line(film, formats=(), version=""):
    """The metadata line under a title: runtime first, then how it is being
    projected, then who it is for."""
    bits = [film.runtime]
    if formats:
        bits.append(", ".join(formats))
    if film.rating:
        bits.append(film.rating)
    if version:
        bits.append(version)
    if film.genres:
        bits.append(", ".join(film.genres))
    return SEP.join(bits)


def _title(cell_or_film, strands=()):
    title = getattr(cell_or_film, "title", "")
    marks = f"  ‹{', '.join(strands)}›" if strands else ""
    return f"**{title}**{marks}"


def block_meta(screenings):
    """Formats offered across a block, in table order, plus the version if the
    whole block agrees on one. Shared by every caller so the header line is
    built the same way everywhere."""
    union = []
    for s in screenings:
        for f in s.formats:
            if f not in union:
                union.append(f)
    versions = {s.version for s in screenings if s.version}
    return union, (versions.pop() if len(versions) == 1 else "")


def screening_rows(screenings, show_version=None):
    """One row per screening.

    The version is printed per row only when the block actually mixes them --
    otherwise the header already says `OV` and repeating it on every line is
    noise. Pass `show_version` to override the automatic choice.
    """
    if show_version is None:
        show_version = len({s.version for s in screenings if s.version}) > 1
    rows = []
    for s in screenings:
        span = f"{s.start}–{s.end}" if s.end else s.start
        fmt = " ".join(s.formats) if s.formats else NO_FORMAT
        extra = [
            b for b in (
                s.version if show_version else "",
                f"zaal {s.hall}" if s.hall else "",
                *s.notes,
            ) if b
        ]
        rows.append((span, fmt, SEP.join(extra)))
    if not rows:
        return []
    span_w = max(len(r[0]) for r in rows)
    fmt_w = max(len(r[1]) for r in rows)
    return [f"  {a.ljust(span_w)}  {b.ljust(fmt_w)}  {c}".rstrip() for a, b, c in rows]


def cell_block(cell):
    """One film on one date, with its screenings."""
    union, version = block_meta(cell.screenings)
    lines = [_title(cell, cell.strands), film_line(cell.film, union, version)]
    lines.extend(screening_rows(cell.screenings))
    return "\n".join(lines)
def section(heading, blocks, note=""):
    out = [f"## {heading}", ""]
    if blocks:
        out.append("\n\n".join(blocks))
    else:
        out.append("_Geen voorstellingen gevonden._")
    if note:
        out.extend(["", f"_{note}_"])
    return "\n".join(out)


def document(sections, note=""):
    body = "\n\n".join(s for s in sections if s)
    if note:
        body += f"\n\n_{note}_"
    return body.strip() + "\n"
