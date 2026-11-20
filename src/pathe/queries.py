"""The ten operations behind the commands.

Each builds a plain result and returns it rendered -- Markdown by default, JSON
with `as_json` -- by `render`, the only place output is formatted. Kept
separate from `cli` so the MCP adapter and the tests call exactly the same
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


async def _screened(client, catalogue, cinemas, dates, keep, *, include_dubs, include_kids,
                    starts_after, ends_before):
    """`{cinema: [cell, ...]}` for the cells `keep` picks, with screenings.

    Matrix, then the dub/kids filters, then the showtimes fanout for what is
    left, then the time window -- which needs the times, so it comes last.
    Cells the window emptied drop out, as do cells with no screenings at all.
    """
    grouped, dropped = {}, filters.Filtered()
    for cinema in cinemas:
        matrix = await client.cinema_matrix(cinema)
        picked = [c for c in cells(matrix, cinema, catalogue, dates) if keep(c)]
        kept, removed = filters.apply(picked, include_dubs=include_dubs, include_kids=include_kids)
        grouped[cinema] = kept
        dropped.dubs.extend(removed.dubs)
        dropped.kids.extend(removed.kids)
    flat = await _resolve(grouped, client)
    dropped.outside_window = filters.window(flat, starts_after=starts_after,
                                            ends_before=ends_before)
    return {cinema: [c for c in group if c.screenings] for cinema, group in grouped.items()}, dropped


def _cinema_names(cinemas_payload):
    return {c["slug"]: c["name"] for c in cinemas_payload}


def _cinema_cities(cinemas_payload):
    return {c["slug"]: c.get("citySlug") or "" for c in cinemas_payload}


def _also_found(hits):
    return [{"title": f.title, "slug": f.slug} for f in hits[1:4]]


async def list_cinemas(client, *, as_json=False):
    payload = await client.cinemas()
    entries = [
        {
            "slug": c["slug"],
            "name": c["name"],
            "city": c.get("citySlug") or "",
            "formats": tagmod.formats(c.get("tags") or ()),
        }
        for c in payload
    ]
    entries.sort(key=lambda c: (c["city"] or "?", c["name"]))
    result = {"cinemas": entries}
    return render.to_json(result) if as_json else render.cinemas(result)


async def find_film(client, query, limit=10, *, as_json=False):
    catalogue = await _catalogue(client)
    result = {"query": query, "films": catalogue.search(query)[:limit]}
    return render.to_json(result) if as_json else render.search(result)


async def programme(client, cinemas, date, *, include_dubs=False, include_kids=False,
                    links=False, starts_after=None, ends_before=None, as_json=False):
    catalogue = await _catalogue(client)
    names = _cinema_names(await client.cinemas())
    grouped, dropped = await _screened(
        client, catalogue, cinemas, [date], lambda c: True,
        include_dubs=include_dubs, include_kids=include_kids,
        starts_after=starts_after, ends_before=ends_before,
    )
    result = {
        "date": date,
        "cinemas": [{"slug": c, "name": names.get(c, c), "films": grouped[c]} for c in cinemas],
        "filtered": dropped,
    }
    return render.to_json(result) if as_json else render.programme(result, links=links)


async def film_showtimes(client, query, cinemas, dates, *, include_dubs=True, include_kids=True,
                         links=False, starts_after=None, ends_before=None, as_json=False):
    """Times for one film. Filters default to *off* here: if you asked for a
    specific title by name you meant that title, dub or not. The time window
    still applies when given -- that is a question about the evening, not the film."""
    catalogue = await _catalogue(client)
    names = _cinema_names(await client.cinemas())
    hits = catalogue.search(query)
    result = {"query": query, "film": None, "cinemas": [], "filtered": filters.Filtered(),
              "also_found": []}
    if hits:
        film = hits[0]
        grouped, dropped = await _screened(
            client, catalogue, cinemas, dates, lambda c: c.film.slug == film.slug,
            include_dubs=include_dubs, include_kids=include_kids,
            starts_after=starts_after, ends_before=ends_before,
        )
        result.update(
            film=film,
            cinemas=[{"slug": c, "name": names.get(c, c), "days": grouped[c]} for c in cinemas],
            filtered=dropped,
            also_found=_also_found(hits),
        )
    return render.to_json(result) if as_json else render.film(result, links=links)


async def where(client, query, mine, dates, *, only_favorites=False, as_json=False):
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
    result = {"query": query, "film": None, "cinema_count": 0, "total_cinemas": 0,
              "only_favorites": only_favorites, "mine": [], "missing": [], "elsewhere": [],
              "also_found": []}
    if not hits:
        return render.to_json(result) if as_json else render.where(result)
    film = hits[0]

    playing = playing_dates(await client.show_cinemas(film.slug), dates)
    cinemas_payload = await client.cinemas()
    names = _cinema_names(cinemas_payload)
    cities = _cinema_cities(cinemas_payload)

    def entry(slug):
        return {"slug": slug, "name": names.get(slug, slug), "dates": playing[slug]}

    rest = sorted(
        (c for c in playing if c not in mine),
        key=lambda c: (cities.get(c, ""), names.get(c, c)),
    )
    result.update(
        film=film,
        cinema_count=len(playing),
        total_cinemas=len(cinemas_payload),
        mine=[entry(c) for c in mine if c in playing],
        missing=[c for c in mine if c not in playing],
        elsewhere=[] if only_favorites else [entry(c) for c in rest],
        also_found=_also_found(hits),
    )
    return render.to_json(result) if as_json else render.where(result)


async def _strand(client, label, keep, cinemas, dates, *, include_dubs, include_kids,
                  links, starts_after, ends_before, as_json):
    catalogue = await _catalogue(client)
    names = _cinema_names(await client.cinemas())
    grouped, dropped = await _screened(
        client, catalogue, cinemas, dates, keep,
        include_dubs=include_dubs, include_kids=include_kids,
        starts_after=starts_after, ends_before=ends_before,
    )
    result = {
        "strand": label,
        "cinemas": [{"slug": c, "name": names.get(c, c), "films": grouped[c]} for c in cinemas],
        "filtered": dropped,
    }
    return render.to_json(result) if as_json else render.strand(result, links=links)


async def tagged(client, tag, cinemas, dates, *, include_dubs=False, include_kids=False,
                 links=False, starts_after=None, ends_before=None, as_json=False):
    """Every screening carrying `tag` in the window -- the Arthouse, Pride
    Night and Classics view, and anything else Pathé tags."""
    return await _strand(
        client, tagmod.STRANDS.get(tag, tag), lambda c: tag in c.tags, cinemas, dates,
        include_dubs=include_dubs, include_kids=include_kids, links=links,
        starts_after=starts_after, ends_before=ends_before, as_json=as_json,
    )


async def new(client, cinemas, dates, *, include_dubs=False, include_kids=False,
              links=False, starts_after=None, ends_before=None, as_json=False):
    """Screenings of the titles Pathé flags `isNew` -- in practice, released
    in roughly the last week, which is why the CLI defaults to seven days."""
    return await _strand(
        client, "Nieuw", lambda c: c.film.is_new, cinemas, dates,
        include_dubs=include_dubs, include_kids=include_kids, links=links,
        starts_after=starts_after, ends_before=ends_before, as_json=as_json,
    )


async def upcoming(client, limit=25, *, include_dubs=False, include_kids=False, as_json=False):
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
    result = {"total": len(pending), "films": kept, "filtered": dropped}
    return render.to_json(result) if as_json else render.upcoming(result)


async def film_info(client, query, *, as_json=False):
    """One title in depth: cast, synopsis, Kijkwijzer, trailer. The catalogue
    has none of that, so this costs one `/api/show/<slug>` on top."""
    catalogue = await _catalogue(client)
    hits = catalogue.search(query)
    result = {"query": query, "film": None, "details": None, "also_found": []}
    if hits:
        film = hits[0]
        result.update(film=film, also_found=_also_found(hits))
        show = await client.show(film.slug)
        if isinstance(show, dict) and show:
            trailers = show.get("trailers") or []
            trailer = next((t for t in trailers if t.get("language") == "nl"),
                           trailers[0] if trailers else {})
            original = (show.get("originalTitle") or "").strip()
            result["details"] = {
                "cast": [a.strip() for a in (show.get("actors") or "").split(",") if a.strip()],
                "original_title": original if original and original != film.title else None,
                "content_warnings": [c["description"] for c in show.get("cinechecks") or []
                                     if c.get("description")],
                "synopsis": render.plain_text(show.get("synopsis")),
                "trailer_url": trailer.get("externalId") or None,
            }
    return render.to_json(result) if as_json else render.info(result)


async def cinema_info(client, slug, *, as_json=False):
    """One cinema in detail, from the `/api/cinemas` payload `cinemas` already
    fetches. `slug` must already be resolved."""
    raw = next(c for c in await client.cinemas() if c["slug"] == slug)
    result = {
        "slug": raw["slug"],
        "name": raw["name"],
        "addresses": [
            {
                "name": t.get("name") or "",
                "street": t.get("addressLine1") or "",
                "street2": t.get("addressLine2") or "",
                "postcode": t.get("addressZip") or "",
                "city": t.get("addressCity") or "",
            }
            for t in raw.get("theaters") or []
        ],
        "halls": raw.get("hallCount"),
        "seats": raw.get("seatCount"),
        "formats": tagmod.formats(raw.get("tags") or ()),
        # No `hasPmrService`: it is false for all 31 cinemas, Helmond included,
        # whose own services text says every hall is wheelchair accessible. The
        # flag cannot be trusted; the services list carries the real information.
        "services": [
            {
                "label": s.get("label") or "",
                "description": render.plain_text(s.get("description")),
                "accessibility": bool(s.get("isAccessibility")),
            }
            for s in raw.get("services") or []
        ],
        "maps_url": raw.get("googleMyBusinessUrl") or None,
    }
    return render.to_json(result) if as_json else render.cinema(result)
