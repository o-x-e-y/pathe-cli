"""Joining the national catalogue to a cinema matrix."""

from conftest import CINEMA, MONDAY, SUNDAY, load

from pathe.catalogue import cells, date_range, parse_screenings


def test_indexes_the_catalogue(catalogue):
    assert len(catalogue.films) == 240
    film = catalogue.get("spider-man-brand-new-day-48103")
    assert film.title == "Spider-Man: Brand New Day"
    assert film.duration == 145
    assert film.rating == "-12 jaar"
    assert film.genres == ("Actie", "Avontuur")
    assert film.directors == ("Destin Daniel Cretton",)


def test_runtime_formatting(catalogue):
    assert catalogue.get("spider-man-brand-new-day-48103").runtime == "145 min"
    assert catalogue.get("not-a-real-slug-1").runtime == "duur onbekend"


def test_unknown_slug_becomes_a_readable_stub(catalogue):
    """One-off events sometimes appear in a matrix but not in /api/shows. They
    must still render rather than disappear from the programme."""
    film = catalogue.get("een-of-ander-evenement-99999")
    assert film.title == "Een Of Ander Evenement"
    assert film.slug == "een-of-ander-evenement-99999"


def test_search_prefers_exact_then_shortest(catalogue):
    hits = catalogue.search("spider-man")
    assert hits[0].title.startswith("Spider-Man")


def test_search_is_case_and_accent_insensitive(catalogue):
    assert catalogue.search("SPIDER-MAN")
    assert catalogue.search("andre rieu"), "accent-folded search should find André Rieu"


def test_search_matches_slug_too(catalogue):
    assert catalogue.search("spider-man-brand-new-day-48103")


def test_search_empty_for_nonsense(catalogue):
    assert catalogue.search("zzzzzzzzzz") == []


def test_upcoming_is_ordered_and_only_coming_soon(catalogue):
    pending = catalogue.upcoming()
    assert len(pending) == 177
    assert all(f.coming_soon for f in pending)
    orders = [f.upcoming_order for f in pending if f.upcoming_order is not None]
    assert orders == sorted(orders)


def test_date_range():
    import datetime as dt

    assert date_range(3, dt.date(2026, 9, 13)) == ["2026-09-13", "2026-09-14", "2026-09-15"]
    assert date_range(0, dt.date(2026, 9, 13)) == []


def test_cells_only_returns_requested_dates(catalogue):
    matrix = load(f"cinema-{CINEMA}.json")
    got = cells(matrix, CINEMA, catalogue, [SUNDAY])
    assert got, "Helmond has a programme on the recorded Sunday"
    assert {c.date for c in got} == {SUNDAY}


def test_cells_carry_the_matrix_metadata(catalogue):
    """Everything the filters need is present without a showtimes request."""
    matrix = load(f"cinema-{CINEMA}.json")
    got = cells(matrix, CINEMA, catalogue, [SUNDAY, MONDAY])
    assert any(c.versions for c in got)
    assert any(c.tags for c in got)
    assert any(c.is_kids for c in got), "the kids flag must survive the join"


def test_cells_are_sorted_deterministically(catalogue):
    matrix = load(f"cinema-{CINEMA}.json")
    got = cells(matrix, CINEMA, catalogue, [SUNDAY, MONDAY])
    assert [(c.date, c.film.title) for c in got] == sorted((c.date, c.film.title) for c in got)


def test_cells_ignores_dates_outside_the_window(catalogue):
    matrix = load(f"cinema-{CINEMA}.json")
    assert cells(matrix, CINEMA, catalogue, ["1999-01-01"]) == []


def test_in_the_picture_lands_on_the_sunday(catalogue):
    """The strand this tool exists to surface: Sunday and Monday, one title
    each, at ~19:00."""
    matrix = load(f"cinema-{CINEMA}.json")
    sunday = [c for c in cells(matrix, CINEMA, catalogue, [SUNDAY]) if "in-the-picture" in c.tags]
    monday = [c for c in cells(matrix, CINEMA, catalogue, [MONDAY]) if "in-the-picture" in c.tags]
    assert len(sunday) == 1 and len(monday) == 1
    assert sunday[0].film.slug != monday[0].film.slug, "the A/B pair are different titles"


def test_cell_strands_merge_tag_and_catalogue_type(catalogue):
    matrix = load(f"cinema-{CINEMA}.json")
    got = [c for c in cells(matrix, CINEMA, catalogue, [SUNDAY]) if "in-the-picture" in c.tags]
    assert got[0].strands == ["In the Picture"]


def test_parse_screenings_reads_a_real_payload():
    got = parse_screenings(load("showtimes-spider-arena.json"))
    assert got
    first = got[0]
    assert len(first.start) == 5 and ":" in first.start
    assert len(first.end) == 5
    assert first.version == "OV"
    assert first.hall
    # The recorded Arena day includes 4DX 3D screenings.
    assert any("4DX" in s.formats and "3D" in s.formats for s in got)
    # ...and plain ones.
    assert any(s.formats == () for s in got)


def test_parse_screenings_is_time_sorted():
    got = parse_screenings(load("showtimes-spider-arena.json"))
    assert [s.start for s in got] == sorted(s.start for s in got)


def test_parse_screenings_handles_empty():
    assert parse_screenings([]) == []
    assert parse_screenings(None) == []


def test_playing_dates_keeps_only_dates_in_the_window():
    from pathe.catalogue import playing_dates

    payload = {
        "pathe-arnhem": {"days": {"2026-09-09": {}, "2026-09-10": {}, "2026-09-20": {}}},
    }
    assert playing_dates(payload, ["2026-09-09", "2026-09-10"]) == {
        "pathe-arnhem": ["2026-09-09", "2026-09-10"]
    }


def test_playing_dates_drops_cinemas_with_nothing_in_the_window():
    from pathe.catalogue import playing_dates

    payload = {"pathe-arnhem": {"days": {"2026-09-20": {}}}}
    assert playing_dates(payload, ["2026-09-09"]) == {}


def test_playing_dates_sorts_and_survives_an_empty_payload():
    from pathe.catalogue import playing_dates

    payload = {"pathe-arnhem": {"days": {"2026-09-10": {}, "2026-09-09": {}}}}
    assert playing_dates(payload, ["2026-09-09", "2026-09-10"])["pathe-arnhem"] == [
        "2026-09-09",
        "2026-09-10",
    ]
    assert playing_dates({}, ["2026-09-09"]) == {}
