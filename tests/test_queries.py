"""The five operations, end to end against recorded fixtures."""

import pytest
from conftest import CINEMA, MONDAY, SUNDAY

from pathe import queries

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_list_cinemas_groups_by_city(client):
    out = await queries.list_cinemas(client)
    assert "Pathé bioscopen (31)" in out
    assert "`pathe-helmond`" in out
    assert "**amsterdam**" in out
    # Format capability is what makes the list worth printing.
    assert "IMAX" in out and "4DX" in out


async def test_programme_renders_films_with_runtime_first(client):
    out = await queries.programme(client, [CINEMA], SUNDAY)
    assert "zondag 13 september 2026" in out
    assert "**" in out
    assert " min · " in out


async def test_programme_filters_dubs_and_kids_by_default(client):
    filtered = await queries.programme(client, [CINEMA], SUNDAY)
    unfiltered = await queries.programme(
        client, [CINEMA], SUNDAY, include_dubs=True, include_kids=True
    )
    assert "gefilterd:" in filtered
    assert "gefilterd:" not in unfiltered
    assert len(unfiltered) > len(filtered)


async def test_programme_names_what_it_removed(client):
    """Nothing disappears silently -- the point of the `gefilterd:` line."""
    out = await queries.programme(client, [CINEMA], SUNDAY)
    note = out.rsplit("gefilterd:", 1)[1]
    assert "kinderfilm" in note or "nagesynchroniseerd" in note


async def test_filtering_happens_before_the_fanout(client):
    """The cost argument for the whole design: a filtered title must never
    cost a showtimes request."""
    await queries.programme(client, [CINEMA], SUNDAY)
    filtered_calls = len(client.showtime_calls)

    wide = type(client)()
    await queries.programme(wide, [CINEMA], SUNDAY, include_dubs=True, include_kids=True)
    assert filtered_calls < len(wide.showtime_calls)


async def test_programme_costs_one_matrix_request_per_cinema(client):
    await queries.programme(client, [CINEMA], SUNDAY)
    assert client.calls.count(f"matrix:{CINEMA}") == 1


async def test_programme_never_polls_a_date_blindly(client):
    """Every showtimes request corresponds to a cell the matrix said exists."""
    await queries.programme(client, [CINEMA], SUNDAY)
    assert all(call.endswith(SUNDAY) for call in client.showtime_calls)


async def test_arthouse_finds_the_sunday_monday_pair(client):
    out = await queries.tagged(client, "in-the-picture", [CINEMA], [SUNDAY, MONDAY])
    assert "In the Picture" in out
    assert "zondag 13 september 2026" in out
    assert "maandag 14 september 2026" in out


async def test_arthouse_screenings_are_evening(client):
    out = await queries.tagged(client, "in-the-picture", [CINEMA], [SUNDAY, MONDAY])
    assert "19:" in out or "20:" in out


async def test_classics_strand(client):
    out = await queries.tagged(client, "classics", [CINEMA], [SUNDAY, MONDAY])
    assert "Classics" in out


async def test_tagged_empty_strand_says_so(client):
    out = await queries.tagged(client, "pridenight", [CINEMA], [SUNDAY])
    assert "Geen voorstellingen gevonden" in out


async def test_tagged_only_fetches_matching_cells(client):
    """A strand query must not pay for the whole day's programme."""
    await queries.tagged(client, "in-the-picture", [CINEMA], [SUNDAY, MONDAY])
    strand_calls = len(client.showtime_calls)

    whole_day = type(client)()
    await queries.programme(whole_day, [CINEMA], SUNDAY)
    assert strand_calls < len(whole_day.showtime_calls)


async def test_film_showtimes_groups_by_date(client):
    out = await queries.film_showtimes(client, "fuori", [CINEMA], [SUNDAY, MONDAY])
    assert out.startswith("# ")
    assert "zondag 13 september 2026" in out


async def test_film_showtimes_does_not_filter(client):
    """Asking for a title by name means that title, dub or not."""
    out = await queries.film_showtimes(client, "toy story 5", [CINEMA], [SUNDAY, MONDAY])
    assert "gefilterd:" not in out


async def test_film_showtimes_suggests_alternatives(client):
    out = await queries.film_showtimes(client, "the", [CINEMA], [SUNDAY])
    assert "ook gevonden:" in out


async def test_film_showtimes_unknown_title(client):
    out = await queries.film_showtimes(client, "zzzzzzz", [CINEMA], [SUNDAY])
    assert "Geen voorstellingen gevonden" in out


async def test_upcoming_costs_one_request(client):
    out = await queries.upcoming(client, limit=5)
    assert "Binnenkort" in out
    assert client.showtime_calls == [], "coming-soon needs no fanout at all"


async def test_upcoming_respects_limit(client):
    out = await queries.upcoming(client, limit=3)
    assert out.count("release ") + out.count("datum onbekend") == 3


async def test_upcoming_filters_dubs(client):
    filtered = await queries.upcoming(client, limit=200)
    unfiltered = await queries.upcoming(client, limit=200, include_dubs=True)
    assert "Nederlandse versie" not in filtered.split("gefilterd:")[0]
    assert len(unfiltered) >= len(filtered)


async def test_find_film_reports_slug_and_runtime(client):
    out = await queries.find_film(client, "spider-man")
    assert "Spider-Man" in out
    assert "145 min" in out
    assert "`spider-man-brand-new-day-48103`" in out


async def test_multiple_cinemas_get_their_own_section(client):
    out = await queries.programme(client, [CINEMA, "pathe-eindhoven"], SUNDAY)
    assert out.count("## ") == 2


async def test_output_is_byte_identical_across_runs(client):
    """The copy-verbatim guarantee, at the level the user actually sees."""
    a = await queries.programme(client, [CINEMA], SUNDAY)
    b = await queries.programme(type(client)(), [CINEMA], SUNDAY)
    assert a == b


async def test_show_cinemas_is_one_request(client):
    """The whole point of the endpoint: the field is one call, not 31."""
    from pathe.api import PatheClient

    assert hasattr(PatheClient, "show_cinemas")
    payload = await client.show_cinemas("leviticus-53403")
    assert set(payload) and client.calls == ["show_cinemas:leviticus-53403"]


FOUR = [
    "pathe-helmond",
    "pathe-eindhoven",
    "pathe-tilburg-centrum",
    "pathe-tilburg-stappegoor",
]
WEEK = [f"2026-09-{d:02d}" for d in range(9, 17)]


async def test_where_splits_mine_from_the_rest(client):
    out = await queries.where(client, "leviticus", FOUR, WEEK)
    assert out.startswith("# Leviticus — 9 van 31 bioscopen")
    assert "## Jouw bioscopen" in out
    assert "`pathe-tilburg-stappegoor`" in out.split("## Elders")[0]
    assert "`pathe-arena`" in out.split("## Elders")[1]


async def test_where_names_the_favourites_that_do_not_have_it(client):
    """An empty first section would be ambiguous -- no cinemas, or no
    favourites configured?"""
    out = await queries.where(client, "leviticus", FOUR, WEEK)
    mine = out.split("## Elders")[0]
    assert "niet in: helmond, eindhoven, tilburg-centrum" in mine


async def test_where_counts_the_others(client):
    out = await queries.where(client, "leviticus", FOUR, WEEK)
    assert "## Elders (8)" in out


async def test_where_only_favourites_drops_the_rest(client):
    out = await queries.where(client, "leviticus", FOUR, WEEK, only_favorites=True)
    assert "## Jouw bioscopen" in out and "## Elders" not in out


async def test_where_narrows_to_the_window(client):
    out = await queries.where(client, "leviticus", FOUR, ["2026-09-09"])
    assert "wo 9 sep" in out and "wo 16 sep" not in out


async def test_where_fetches_no_showtimes(client):
    """`where` answers where, not when. Pulling showtimes would put the
    31-cinema cost straight back in."""
    await queries.where(client, "leviticus", FOUR, WEEK)
    assert client.showtime_calls == []


async def test_where_on_an_unknown_title(client):
    out = await queries.where(client, "zzzznietbestaand", FOUR, WEEK)
    assert "Zoeken: “zzzznietbestaand”" in out


async def test_where_when_the_title_plays_nowhere(client):
    """Known title, no cinemas in the window -- say so, rather than printing
    two empty sections."""
    out = await queries.where(client, "leviticus", FOUR, ["2027-01-01"])
    assert "draait nergens in dit venster" in out
    assert "## Elders" not in out


async def test_where_notes_other_title_matches(client):
    """Same affordance `film` has: the catalogue title often differs from the
    spoken one, so name the near misses."""
    out = await queries.where(client, "the", FOUR, WEEK)
    assert "ook gevonden:" in out
