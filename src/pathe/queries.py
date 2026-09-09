"""The seven operations, each returning finished Markdown.

Kept separate from `cli` so the MCP adapter and the tests call exactly the same
code paths the terminal does -- there is no second rendering path to drift.
"""

from . import filters, render
from . import tags as tagmod
from .catalogue import Catalogue, cells, parse_screenings, playing_dates


async def _catalogue(client):
    return Catalogue(await client.shows())


async def _resolve(cells_by_cinema, client):
    """Fetch showtimes for every surviving cell, in one concurrent batch."""
    flat = [c for group in cells_by_cinema.values() for c in group]
    triples = [(c.film.slug, c.cinema, c.date) for c in flat]
    fetched = await client.gather_showtimes(triples)
    for cell in flat:
        cell.screenings = parse_screenings(fetched.get((cell.film.slug, cell.cinema, cell.date)))
    return flat


def _cinema_names(cinemas_payload):
    return {c["slug"]: c["name"] for c in cinemas_payload}


def _cinema_cities(cinemas_payload):
    return {c["slug"]: c.get("citySlug") or "" for c in cinemas_payload}


def _short(slug):
    """`pathe-helmond` -> `helmond`. For prose, where the prefix is noise."""
    return slug[len("pathe-"):] if slug.startswith("pathe-") else slug


async def list_cinemas(client):
    payload = await client.cinemas()
    by_city = {}
    for cinema in payload:
        by_city.setdefault(cinema.get("citySlug") or "?", []).append(cinema)
    blocks = []
    for city in sorted(by_city):
        lines = [f"**{city}**"]
        for cinema in sorted(by_city[city], key=lambda c: c["name"]):
            formats = tagmod.formats(cinema.get("tags") or ())
            suffix = f" — {', '.join(formats)}" if formats else ""
            lines.append(f"  `{cinema['slug']}`  {cinema['name']}{suffix}")
        blocks.append("\n".join(lines))
    return render.document([render.section(f"Pathé bioscopen ({len(payload)})", blocks)])


async def find_film(client, query, limit=10):
    catalogue = await _catalogue(client)
    hits = catalogue.search(query)[:limit]
    blocks = []
    for film in hits:
        head = f"**{film.title}**"
        strand = film.strand or film.label
        if strand:
            head += f"  ‹{strand}›"
        meta = render.film_line(film)
        extra = [f"`{film.slug}`"]
        if film.release:
            extra.append(f"release {film.release}")
        if film.coming_soon:
            extra.append("binnenkort")
        blocks.append(f"{head}\n{meta}\n{render.SEP.join(extra)}")
    return render.document([render.section(f"Zoeken: “{query}”", blocks)])


async def programme(client, cinemas, date, *, include_dubs=False, include_kids=False):
    catalogue = await _catalogue(client)
    names = _cinema_names(await client.cinemas())
    grouped, dropped = {}, filters.Filtered()
    for cinema in cinemas:
        matrix = await client.cinema_matrix(cinema)
        kept, removed = filters.apply(
            cells(matrix, cinema, catalogue, [date]),
            include_dubs=include_dubs,
            include_kids=include_kids,
        )
        grouped[cinema] = kept
        dropped.dubs.extend(removed.dubs)
        dropped.kids.extend(removed.kids)
    await _resolve(grouped, client)

    sections = []
    for cinema in cinemas:
        blocks = [render.cell_block(c) for c in grouped[cinema] if c.screenings]
        heading = f"{names.get(cinema, cinema)} — {render.dutch_date(date)}"
        sections.append(render.section(heading, blocks))
    return render.document(sections, note=_note(dropped))


async def film_showtimes(client, query, cinemas, dates, *, include_dubs=True, include_kids=True):
    """Times for one film. Filters default to *off* here: if you asked for a
    specific title by name you meant that title, dub or not."""
    catalogue = await _catalogue(client)
    names = _cinema_names(await client.cinemas())
    hits = catalogue.search(query)
    if not hits:
        return render.document([render.section(f"Zoeken: “{query}”", [])])
    film = hits[0]

    grouped, dropped = {}, filters.Filtered()
    for cinema in cinemas:
        matrix = await client.cinema_matrix(cinema)
        picked = [c for c in cells(matrix, cinema, catalogue, dates) if c.film.slug == film.slug]
        kept, removed = filters.apply(picked, include_dubs=include_dubs, include_kids=include_kids)
        grouped[cinema] = kept
        dropped.dubs.extend(removed.dubs)
        dropped.kids.extend(removed.kids)
    await _resolve(grouped, client)

    sections = []
    for cinema in cinemas:
        blocks = []
        for cell in sorted(grouped[cinema], key=lambda c: c.date):
            if not cell.screenings:
                continue
            union, version = render.block_meta(cell.screenings)
            heading = f"**{render.dutch_date(cell.date)}**"
            marks = " · ".join(x for x in (", ".join(union), version) if x)
            if marks:
                heading += f"  {marks}"
            rows = render.screening_rows(cell.screenings)
            blocks.append("\n".join([heading, *rows]))
        sections.append(render.section(names.get(cinema, cinema), blocks))
    header = f"# {film.title}\n{render.film_line(film)}"
    other = [f for f in hits[1:4]]
    note = _note(dropped)
    if other:
        alts = ", ".join(f"{f.title} (`{f.slug}`)" for f in other)
        note = (note + "  " if note else "") + f"ook gevonden: {alts}"
    return header + "\n\n" + render.document(sections, note=note)



async def where(client, query, mine, dates, *, only_favorites=False):
    """Which cinemas play one title -- the field, not the times.

    Costs one `show_cinemas` request plus the two catalogue ones, because the
    endpoint is the cinema matrix seen from the film's side and already lists
    only the cinemas that have it. Asking the same question through
    `film_showtimes` means a matrix request per cinema and a showtimes fanout
    on top, for an answer you were going to narrow anyway.

    Deliberately fetches no showtimes: `where` is the step before `film`.
    """
    catalogue = await _catalogue(client)
    hits = catalogue.search(query)
    if not hits:
        return render.document([render.section(f"Zoeken: “{query}”", [])])
    film = hits[0]

    playing = playing_dates(await client.show_cinemas(film.slug), dates)
    cinemas_payload = await client.cinemas()
    names = _cinema_names(cinemas_payload)
    cities = _cinema_cities(cinemas_payload)

    header = (
        f"# {film.title} — {len(playing)} van {len(cinemas_payload)} bioscopen\n"
        f"{render.film_line(film)}"
    )
    note = ""
    other = hits[1:4]
    if other:
        note = "ook gevonden: " + ", ".join(f"{f.title} (`{f.slug}`)" for f in other)

    if not playing:
        body = "_draait nergens in dit venster._"
        if note:
            body += f"\n\n_{note}_"
        return f"{header}\n\n{body}\n"

    kept = [c for c in mine if c in playing]
    missing = [c for c in mine if c not in playing]
    rest = sorted(
        (c for c in playing if c not in mine),
        key=lambda c: (cities.get(c, ""), names.get(c, c)),
    )

    blocks = render.cinema_rows([(c, names.get(c, c), playing[c]) for c in kept])
    if missing:
        blocks.append("niet in: " + ", ".join(_short(c) for c in missing))
    sections = [render.section("Jouw bioscopen", blocks)]
    if not only_favorites:
        sections.append(
            render.section(
                f"Elders ({len(rest)})",
                render.cinema_rows([(c, names.get(c, c), playing[c]) for c in rest]),
            )
        )
    return header + "\n\n" + render.document(sections, note=note)


async def tagged(client, tag, cinemas, dates, *, include_dubs=False, include_kids=False):
    """Every screening carrying `tag` in the window -- the Arthouse, Pride
    Night and Classics view, and anything else Pathé tags."""
    catalogue = await _catalogue(client)
    names = _cinema_names(await client.cinemas())
    grouped, dropped = {}, filters.Filtered()
    for cinema in cinemas:
        matrix = await client.cinema_matrix(cinema)
        picked = [c for c in cells(matrix, cinema, catalogue, dates) if tag in c.tags]
        kept, removed = filters.apply(picked, include_dubs=include_dubs, include_kids=include_kids)
        grouped[cinema] = kept
        dropped.dubs.extend(removed.dubs)
        dropped.kids.extend(removed.kids)
    await _resolve(grouped, client)

    label = tagmod.STRANDS.get(tag, tag)
    sections = []
    for cinema in cinemas:
        blocks = []
        for cell in sorted(grouped[cinema], key=lambda c: (c.date, c.film.title)):
            if not cell.screenings:
                continue
            union, version = render.block_meta(cell.screenings)
            rows = render.screening_rows(cell.screenings)
            blocks.append(
                "\n".join([f"**{render.dutch_date(cell.date)}** — {cell.film.title}",
                           render.film_line(cell.film, union, version), *rows])
            )
        sections.append(render.section(f"{label} — {names.get(cinema, cinema)}", blocks))
    return render.document(sections, note=_note(dropped))


async def upcoming(client, limit=25, *, include_dubs=False, include_kids=False):
    """Coming-soon titles nationally. Answered entirely from `/api/shows` --
    one request, no fanout."""
    catalogue = await _catalogue(client)
    pending = catalogue.upcoming()
    kept = [
        f for f in pending
        if (include_dubs or not filters.is_dub(f.title))
    ][:limit]
    dropped = filters.Filtered(
        dubs=[f.title for f in pending if not include_dubs and filters.is_dub(f.title)]
    )
    blocks = []
    for film in kept:
        head = f"**{film.title}**"
        if film.strand:
            head += f"  ‹{film.strand}›"
        line = render.film_line(film)
        when = f"release {film.release}" if film.release else "datum onbekend"
        blocks.append(f"{head}\n{line}\n{when} · `{film.slug}`")
    return render.document(
        [render.section(f"Binnenkort ({len(kept)} van {len(pending)})", blocks)],
        note=_note(dropped),
    )


def _note(dropped):
    return dropped.summary() if dropped else ""
