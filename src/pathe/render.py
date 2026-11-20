"""Markdown and JSON rendering.

Every command renders through the helpers here, so a film looks identical no
matter which one produced it, and the same query twice produces byte-identical
output you can paste somewhere without it drifting between runs.

Each query in `queries` builds a plain result -- dicts with English keys around
the domain objects -- and picks one of two renderers for it: the per-command
Markdown function below, or `to_json`, which serves every command from the
same result so the two cannot drift apart.
"""

import datetime as dt
import html
import json
import re

from .catalogue import Cell, Film, Screening
from .filters import Filtered

DAYS = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
MONTHS = [
    "januari", "februari", "maart", "april", "mei", "juni",
    "juli", "augustus", "september", "oktober", "november", "december",
]

SHORT_MONTHS = [
    "jan", "feb", "mrt", "apr", "mei", "jun",
    "jul", "aug", "sep", "okt", "nov", "dec",
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


def short_date(iso):
    """`2026-09-16` -> `wo 16 sep`. The long form is for a heading over one
    day's screenings; a list of cinemas needs something that stays in a column.
    """
    try:
        day = dt.date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso
    return f"{DAYS[day.weekday()][:2]} {day.day} {SHORT_MONTHS[day.month - 1]}"


def date_span(days):
    """The run of a film at one cinema.

    Prints the day count when the run has holes in it: a bare `wo 9 – di 15`
    would claim eight days of screenings where there are five, and the gap is
    exactly the thing you would plan around.
    """
    if not days:
        return ""
    first, last = days[0], days[-1]
    if first == last:
        return short_date(first)
    out = f"{short_date(first)} – {short_date(last)}"
    try:
        width = (dt.date.fromisoformat(last) - dt.date.fromisoformat(first)).days + 1
    except (TypeError, ValueError):
        return out
    if len(days) < width:
        out += f" ({len(days)} dagen)"
    return out


def cinema_rows(entries):
    """`[(slug, name, days), ...]` -> one block per cinema.

    The slug gets its own line because it is what you paste into `-c`; the
    names are padded so the spans line up down the block.
    """
    width = max((len(name) for _, name, _ in entries), default=0)
    return [
        f"  `{slug}`\n     {name.ljust(width)}  {date_span(days)}"
        for slug, name, days in entries
    ]


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


def screening_rows(screenings, show_version=None, links=False):
    """One row per screening.

    The version is printed per row only when the block actually mixes them --
    otherwise the header already says `OV` and repeating it on every line is
    noise. Pass `show_version` to override the automatic choice.

    `links` adds the booking URL as a last, bare column, so it copies cleanly.
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
        rows.append((span, fmt, SEP.join(extra), s.booking_url))
    if not rows:
        return []
    span_w = max(len(r[0]) for r in rows)
    fmt_w = max(len(r[1]) for r in rows)
    extra_w = max(len(r[2]) for r in rows)
    out = []
    for a, b, c, url in rows:
        cols = [a.ljust(span_w), b.ljust(fmt_w)]
        if not links:
            cols.append(c)
        else:
            if extra_w:
                cols.append(c.ljust(extra_w))
            cols.append(url)
        out.append(("  " + "  ".join(cols)).rstrip())
    return out


def cell_block(cell, links=False):
    """One film on one date, with its screenings."""
    union, version = block_meta(cell.screenings)
    lines = [_title(cell, cell.strands), film_line(cell.film, union, version)]
    lines.extend(screening_rows(cell.screenings, links=links))
    return "\n".join(lines)


def _label(match):
    parts = re.findall(r"<strong>([^<]*)</strong>", match[1], flags=re.IGNORECASE)
    label = " ".join(re.sub(r"^(?:&nbsp;|\s)+|(?:&nbsp;|\s)+$", "", p) for p in parts)
    label = re.sub(r" (?=[:.,;?!])", "", label)
    rest = match[2]
    after = html.unescape(re.sub(r"<[^>]+>", "", rest)).strip()
    if not after:
        return match[0]
    if after[0] in ":.,;":
        return label + rest
    return label + (" " if html.unescape(label)[-1:] in ".:?!" else ": ") + rest


def plain_text(markup):
    """API HTML as plain lines: tags dropped, entities decoded, blank lines gone.

    A bold run that opens a line is a label -- `Adres`, `1. Parkeergarage X` --
    followed by its text with only an `&nbsp;` between, so it gets a colon
    rather than vanishing into the sentence when the tags go.
    """
    text = re.sub(r"<br\s*/?>|</?p>", "\n", markup or "", flags=re.IGNORECASE)
    text = re.sub(r"^[^\S\n]*((?:<strong>[^<]*</strong>)+)(.*)$", _label, text,
                  flags=re.IGNORECASE | re.MULTILINE)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


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


def _search_miss(query):
    return document([section(f"Zoeken: “{query}”", [])])


def _also_found(entries):
    if not entries:
        return ""
    return "ook gevonden: " + ", ".join(f"{f['title']} (`{f['slug']}`)" for f in entries)


def _short(slug):
    """`pathe-helmond` -> `helmond`. For prose, where the prefix is noise."""
    return slug.removeprefix("pathe-")


# ------------------------------------------------------------ one per command

def cinemas(result):
    by_city = {}
    for cinema in result["cinemas"]:
        by_city.setdefault(cinema["city"] or "?", []).append(cinema)
    blocks = []
    for city, entries in by_city.items():
        lines = [f"**{city}**"]
        for cinema in entries:
            suffix = f" — {', '.join(cinema['formats'])}" if cinema["formats"] else ""
            lines.append(f"  `{cinema['slug']}`  {cinema['name']}{suffix}")
        blocks.append("\n".join(lines))
    return document([section(f"Pathé bioscopen ({len(result['cinemas'])})", blocks)])


def search(result):
    blocks = []
    for film in result["films"]:
        head = f"**{film.title}**"
        strand = film.strand or film.label
        if strand:
            head += f"  ‹{strand}›"
        extra = [f"`{film.slug}`"]
        if film.release:
            extra.append(f"release {film.release}")
        if film.coming_soon:
            extra.append("binnenkort")
        blocks.append(f"{head}\n{film_line(film)}\n{SEP.join(extra)}")
    return document([section(f"Zoeken: “{result['query']}”", blocks)])


def programme(result, links=False):
    sections = []
    for cinema in result["cinemas"]:
        blocks = [cell_block(c, links) for c in cinema["films"]]
        sections.append(section(f"{cinema['name']} — {dutch_date(result['date'])}", blocks))
    return document(sections, note=result["filtered"].summary())


def film(result, links=False):
    found = result["film"]
    if found is None:
        return _search_miss(result["query"])
    sections = []
    for cinema in result["cinemas"]:
        blocks = []
        for cell in cinema["days"]:
            union, version = block_meta(cell.screenings)
            heading = f"**{dutch_date(cell.date)}**"
            marks = SEP.join(x for x in (", ".join(union), version) if x)
            if marks:
                heading += f"  {marks}"
            blocks.append("\n".join([heading, *screening_rows(cell.screenings, links=links)]))
        sections.append(section(cinema["name"], blocks))
    note = "  ".join(n for n in (result["filtered"].summary(), _also_found(result["also_found"])) if n)
    return f"# {found.title}\n{film_line(found)}\n\n" + document(sections, note=note)


def where(result):
    found = result["film"]
    if found is None:
        return _search_miss(result["query"])
    header = (
        f"# {found.title} — {result['cinema_count']} van {result['total_cinemas']} bioscopen\n"
        f"{film_line(found)}"
    )
    note = _also_found(result["also_found"])
    if not result["cinema_count"]:
        body = "_draait nergens in dit venster._"
        if note:
            body += f"\n\n_{note}_"
        return f"{header}\n\n{body}\n"

    # One block per section rather than one per cinema: `section` puts a blank
    # line between blocks, and a list you scan down should stay tight.
    rows = cinema_rows([(c["slug"], c["name"], c["dates"]) for c in result["mine"]])
    if result["missing"]:
        rows.append("  niet in: " + ", ".join(_short(c) for c in result["missing"]))
    sections = [section("Jouw bioscopen", ["\n".join(rows)] if rows else [])]
    if not result["only_favorites"]:
        rest = result["elsewhere"]
        others = cinema_rows([(c["slug"], c["name"], c["dates"]) for c in rest])
        sections.append(section(f"Elders ({len(rest)})", ["\n".join(others)] if others else []))
    return header + "\n\n" + document(sections, note=note)


def strand(result, links=False):
    """`tagged` and `new`: per cinema, date-major, the title on the date line."""
    sections = []
    for cinema in result["cinemas"]:
        blocks = []
        for cell in cinema["films"]:
            union, version = block_meta(cell.screenings)
            blocks.append("\n".join([
                f"**{dutch_date(cell.date)}** — {cell.film.title}",
                film_line(cell.film, union, version),
                *screening_rows(cell.screenings, links=links),
            ]))
        sections.append(section(f"{result['strand']} — {cinema['name']}", blocks))
    return document(sections, note=result["filtered"].summary())


def upcoming(result):
    blocks = []
    for film in result["films"]:
        head = f"**{film.title}**"
        if film.strand:
            head += f"  ‹{film.strand}›"
        when = f"release {film.release}" if film.release else "datum onbekend"
        blocks.append(f"{head}\n{film_line(film)}\n{when}{SEP}`{film.slug}`")
    heading = f"Binnenkort ({len(result['films'])} van {result['total']})"
    return document([section(heading, blocks)], note=result["filtered"].summary())


def info(result):
    found = result["film"]
    if found is None:
        return _search_miss(result["query"])
    details = result["details"]
    facts = []
    if found.directors:
        facts.append(f"regie: {', '.join(found.directors)}")
    if details and details["cast"]:
        facts.append(f"met: {', '.join(details['cast'])}")
    if details and details["original_title"]:
        facts.append(f"originele titel: {details['original_title']}")
    if found.release:
        facts.append(f"release: {dutch_date(found.release)}")
    if details and details["content_warnings"]:
        facts.append(f"kijkwijzer: {', '.join(details['content_warnings'])}")
    if details and details["trailer_url"]:
        facts.append(f"trailer: {details['trailer_url']}")
    parts = [f"# {found.title}\n{film_line(found)}"]
    if facts:
        parts.append("\n".join(facts))
    if details is None:
        parts.append("_Pathé heeft geen details voor deze film._")
    elif details["synopsis"]:
        parts.append(details["synopsis"])
    note = _also_found(result["also_found"])
    if note:
        parts.append(f"_{note}_")
    return "\n\n".join(parts) + "\n"


def cinema(result):
    lines = [f"# {result['name']}"]
    for place in result["addresses"]:
        town = f"{place['postcode']} {place['city']}".strip()
        address = ", ".join(x for x in (place["street"], place["street2"], town) if x)
        if len(result["addresses"]) > 1:
            address = f"{place['name']}: {address}"
        lines.append(address)
    lines.append(f"{result['halls']} zalen{SEP}{result['seats']} stoelen")
    if result["formats"]:
        lines.append(f"formaten: {', '.join(result['formats'])}")
    if result["maps_url"]:
        lines.append(f"kaart: {result['maps_url']}")
    out = "\n".join(lines)
    blocks = []
    for service in result["services"]:
        head = f"**{service['label']}**"
        if service["accessibility"]:
            head += "  ‹toegankelijkheid›"
        blocks.append("\n".join([head, *service["description"].splitlines()]))
    if blocks:
        out += "\n\n" + section("Voorzieningen", blocks)
    return out + "\n"


# ------------------------------------------------------------------------ JSON

def film_json(film, strands=None):
    if strands is None:
        own = film.strand or film.label
        strands = [own] if own else []
    return {
        "slug": film.slug,
        "title": film.title,
        "runtime_min": film.duration or None,
        "rating": film.rating or None,
        "genres": list(film.genres),
        "directors": list(film.directors),
        "strands": list(strands),
        "release": film.release or None,
        "coming_soon": film.coming_soon,
    }


def _minute(moment):
    return moment.strftime("%Y-%m-%dT%H:%M") if moment else None


def screening_json(s):
    return {
        "date": s.starts_at.date().isoformat() if s.starts_at else None,
        "start": _minute(s.starts_at),
        "end": _minute(s.ends_at),
        "hall": s.hall or None,
        "formats": list(s.formats),
        "version": s.version or None,
        "notes": list(s.notes),
        "booking_url": s.booking_url or None,
    }


def _jsonable(obj):
    if isinstance(obj, Cell):
        return {"date": obj.date, "film": film_json(obj.film, obj.strands),
                "screenings": obj.screenings}
    if isinstance(obj, Film):
        return film_json(obj)
    if isinstance(obj, Screening):
        return screening_json(obj)
    if isinstance(obj, Filtered):
        return {"dubs": sorted(set(obj.dubs)), "kids": sorted(set(obj.kids)),
                "outside_time_window": obj.outside_window}
    raise TypeError(f"not JSON-renderable: {type(obj).__name__}")


def to_json(result):
    return json.dumps(result, default=_jsonable, ensure_ascii=False, indent=2) + "\n"
