"""The operations, end to end against recorded fixtures."""

import pytest
from conftest import CINEMA, MONDAY, SUNDAY, FakeClient, load

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


async def test_where_keeps_the_cinema_list_tight(client):
    """One block per section, not one per cinema: `render.section` puts a blank
    line between blocks, and a list you scan should not be double-spaced."""
    out = await queries.where(client, "leviticus", FOUR, WEEK)
    elders = out.split("## Elders")[1]
    assert "\n\n  `pathe-arena`" not in elders
    assert "`pathe-arena`\n     Pathé Arena" in elders


# ------------------------------------------------------------------------ JSON

SCREENING_KEYS = ["date", "start", "end", "hall", "formats", "version", "notes", "booking_url"]
FILM_KEYS = ["slug", "title", "runtime_min", "rating", "genres", "directors", "strands",
             "release", "coming_soon"]


async def test_programme_json_carries_the_same_data(client):
    import json

    got = json.loads(await queries.programme(client, [CINEMA], SUNDAY, as_json=True))
    assert got["date"] == SUNDAY
    (helmond,) = got["cinemas"]
    assert helmond["slug"] == CINEMA and helmond["name"] == "Pathé Helmond"
    fuori = next(f for f in helmond["films"] if f["film"]["title"] == "Fuori")
    assert list(fuori["film"]) == FILM_KEYS
    assert fuori["film"]["strands"] == ["In the Picture"]
    (screening,) = fuori["screenings"]
    assert list(screening) == SCREENING_KEYS
    assert screening["start"] == "2026-09-13T18:45" and screening["hall"] == "1"
    assert screening["booking_url"].startswith("https://"), "present without --links"
    assert got["filtered"]["dubs"][0] == "Minions & Monsters (NL)"
    assert got["filtered"]["outside_time_window"] == 0


async def test_programme_json_lists_what_markdown_lists(client):
    import json

    markdown = await queries.programme(client, [CINEMA], SUNDAY)
    got = json.loads(await queries.programme(client, [CINEMA], SUNDAY, as_json=True))
    titles = [f["film"]["title"] for f in got["cinemas"][0]["films"]]
    assert titles and all(f"**{t}**" in markdown for t in titles)
    assert markdown.count("**") // 2 == len(titles)


async def test_empty_results_are_valid_json_with_empty_lists(client):
    import json

    got = json.loads(await queries.tagged(client, "pridenight", [CINEMA], [SUNDAY], as_json=True))
    assert got["cinemas"][0]["films"] == []
    missing = json.loads(await queries.film_showtimes(client, "zzzzzz", [CINEMA], [SUNDAY],
                                                      as_json=True))
    assert missing["film"] is None and missing["cinemas"] == [] and missing["also_found"] == []
    where = json.loads(await queries.where(client, "zzzzzz", FOUR, WEEK, as_json=True))
    assert where["film"] is None and where["mine"] == [] and where["elsewhere"] == []


async def test_film_json_names_the_other_matches(client):
    import json

    got = json.loads(await queries.film_showtimes(client, "the", [CINEMA], [SUNDAY], as_json=True))
    assert got["also_found"] and set(got["also_found"][0]) == {"title", "slug"}
    assert all(list(day) == ["date", "film", "screenings"] for day in got["cinemas"][0]["days"])


async def test_where_json(client):
    import json

    got = json.loads(await queries.where(client, "leviticus", FOUR, WEEK, as_json=True))
    assert got["cinema_count"] == 9 and got["total_cinemas"] == 31
    assert [c["slug"] for c in got["mine"]] == ["pathe-tilburg-stappegoor"]
    assert got["missing"] == FOUR[:3]
    assert len(got["elsewhere"]) == 8 and got["elsewhere"][0]["dates"]


async def test_upcoming_search_and_cinemas_json(client):
    import json

    upcoming = json.loads(await queries.upcoming(client, limit=3, as_json=True))
    assert upcoming["total"] == 177 and len(upcoming["films"]) == 3
    assert list(upcoming["films"][0]) == FILM_KEYS
    search = json.loads(await queries.find_film(client, "spider-man", as_json=True))
    assert search["films"][0]["slug"] == "spider-man-brand-new-day-48103"
    cinemas = json.loads(await queries.list_cinemas(client, as_json=True))
    assert len(cinemas["cinemas"]) == 31
    assert list(cinemas["cinemas"][0]) == ["slug", "name", "city", "formats"]


# ------------------------------------------------------------- links and times

async def test_links_put_the_booking_url_on_each_row(client):
    out = await queries.programme(client, [CINEMA], SUNDAY, links=True)
    rows = [line for line in out.splitlines() if line.startswith("  ")]
    assert rows and all(row.split()[-1].startswith("https://s.pathe.nl/") for row in rows)
    assert "https://" not in await queries.programme(client, [CINEMA], SUNDAY)


async def test_the_time_window_drops_and_reports(client):
    import datetime as dt

    out = await queries.programme(client, [CINEMA], SUNDAY, starts_after=dt.timedelta(hours=19))
    assert "10:30–" not in out and "21:15–" in out
    assert "14 voorstellingen buiten het tijdvenster" in out
    assert "**By Any Means**" not in out, "a film with nothing left in the window disappears"


async def test_no_time_window_changes_nothing(client):
    """The defaults filter nothing, so the note has no window count and the
    output is the one without the arguments."""
    plain = await queries.programme(client, [CINEMA], SUNDAY)
    assert plain == await queries.programme(client, [CINEMA], SUNDAY,
                                            starts_after=None, ends_before=None)
    assert "tijdvenster" not in plain


async def test_film_applies_the_time_window_though_it_does_not_filter_titles(client):
    import datetime as dt

    out = await queries.film_showtimes(client, "pressure", [CINEMA], [SUNDAY, MONDAY],
                                       starts_after=dt.timedelta(hours=18),
                                       ends_before=dt.timedelta(hours=23))
    assert "21:00–23:00" in out and "20:30–22:30" in out
    assert "10:30–" not in out
    assert "_gefilterd: 3 voorstellingen buiten het tijdvenster_" in out


async def test_tagged_takes_links_and_the_window(client):
    import datetime as dt

    out = await queries.tagged(client, "in-the-picture", [CINEMA], [SUNDAY, MONDAY], links=True,
                               ends_before=dt.timedelta(hours=21))
    assert "Fuori" in out and "https://s.pathe.nl/" in out
    assert "Primavera" not in out, "19:00-21:10 ends after 21:00"


# ------------------------------------------------------------------------- new

async def test_new_lists_only_the_titles_pathe_flags_new(client):
    out = await queries.new(client, [CINEMA], [SUNDAY, MONDAY])
    assert out.startswith("## Nieuw — Pathé Helmond")
    assert "— By Any Means" in out and "— F*ck de Familie" in out
    assert "Spider-Man" not in out


async def test_new_filters_kids_by_default(client):
    out = await queries.new(client, [CINEMA], [SUNDAY, MONDAY])
    assert "gefilterd: 1 kinderfilm (Bumba: Het Circusorkest)" in out
    everything = await queries.new(client, [CINEMA], [SUNDAY, MONDAY], include_kids=True)
    assert "— Bumba: Het Circusorkest" in everything


async def test_new_json(client):
    import json

    got = json.loads(await queries.new(client, [CINEMA], [SUNDAY], as_json=True))
    assert got["strand"] == "Nieuw"
    assert {f["film"]["slug"] for f in got["cinemas"][0]["films"]} == {
        "by-any-means-52350", "f-ck-de-familie-50315",
    }


# ------------------------------------------------------------------------ info

class ShowClient(FakeClient):
    """Serves one hand-made `/api/show` payload for whatever slug is asked."""

    def __init__(self, payload):
        super().__init__()
        self.payload = payload

    async def show(self, slug):
        self.calls.append(f"show:{slug}")
        return self.payload


async def test_info_prints_the_details(client):
    out = await queries.film_info(client, "spider-man")
    assert out.startswith("# Spider-Man: Brand New Day\n145 min · -12 jaar")
    assert "regie: Destin Daniel Cretton" in out
    assert "met: Zendaya, Tom Holland," in out, "the stray space before the comma is gone"
    assert "release: donderdag 30 juli 2026" in out
    assert "kijkwijzer: Geweld, Angst, Grof taalgebruik" in out
    assert "originele titel" not in out, "same as the title, so not repeated"
    assert "Peter Parker" in out
    assert "popcornbucket" not in out and "21448" not in out, "no extraInformation or counts"
    assert "show:spider-man-brand-new-day-48103" in client.calls
    assert not client.showtime_calls


async def test_info_prefers_the_dutch_trailer(client):
    out = await queries.film_info(client, "spider-man")
    assert "trailer: https://" in out and "231766d4" in out, "the nl one, listed first"
    swapped = load("show/spider-man-brand-new-day-48103.json")
    swapped["trailers"].reverse()
    assert "231766d4" in await queries.film_info(ShowClient(swapped), "spider-man")


async def test_info_falls_back_to_the_first_trailer(client):
    out = await queries.film_info(client, "leviticus")
    assert "trailer: https://media.pathe.nl/trailer/video/nl/v/HO00003449/4e0ec758" in out


async def test_info_strips_synopsis_markup_and_shows_a_different_original_title():
    payload = {"synopsis": "<p>Een <em>held</em> &amp; zijn hond.</p>",
               "originalTitle": "Brand New Day", "trailers": []}
    out = await queries.film_info(ShowClient(payload), "spider-man")
    assert "Een held & zijn hond." in out
    assert "originele titel: Brand New Day" in out
    assert "trailer:" not in out


async def test_info_when_pathe_has_no_details():
    """An unknown `/api/show` slug is a 404; the client hands back `[]`."""
    out = await queries.film_info(ShowClient([]), "spider-man")
    assert out.startswith("# Spider-Man: Brand New Day")
    assert "_Pathé heeft geen details voor deze film._" in out


async def test_info_on_an_unknown_title(client):
    out = await queries.film_info(client, "zzzzzz")
    assert "Zoeken: “zzzzzz”" in out
    assert not [c for c in client.calls if c.startswith("show:")]


async def test_info_json(client):
    import json

    spider = json.loads(await queries.film_info(client, "spider-man", as_json=True))
    assert list(spider) == ["query", "film", "details", "also_found"]
    assert list(spider["details"]) == ["cast", "original_title", "content_warnings", "synopsis",
                                       "trailer_url"]
    assert spider["details"]["content_warnings"] == ["Geweld", "Angst", "Grof taalgebruik"]
    assert spider["details"]["original_title"] is None
    other = json.loads(await queries.film_info(client, "the", as_json=True))
    assert other["details"] is None, "no recorded /api/show for it: a 404"
    assert other["also_found"]


# ---------------------------------------------------------------------- cinema

class CinemasClient(FakeClient):
    def __init__(self, payload):
        super().__init__()
        self.payload = payload

    async def cinemas(self):
        return self.payload


async def test_cinema_info_prints_the_practical_details(client):
    out = await queries.cinema_info(client, CINEMA)
    lines = out.splitlines()
    assert lines[:3] == ["# Pathé Helmond", "Frans Joseph van Thielpark 5, 5707 BX Helmond",
                         "6 zalen · 1075 stoelen"]
    assert "kaart: https://maps.google.com/maps?cid=8794382929596725660" in out
    assert "**Parkeren**" in out and "Tarief: € 2,50" in out and "<" not in out
    assert "Welkom bij" not in out, "the marketing description is skipped"
    assert client.calls == ["cinemas"], "no request beyond /api/cinemas"


async def test_cinema_info_with_several_theaters_and_accessibility():
    """hasPmrService is set here to show it stays out even when true."""
    raw = {**load("cinemas.json")[0], "hasPmrService": True, "googleMyBusinessUrl": None}
    raw["theaters"] = [
        {"name": "Zaal Noord", "addressLine1": "Straat 1", "addressZip": "1000 AA",
         "addressCity": "Stad"},
        {"name": "Zaal Zuid", "addressLine1": "Laan 2", "addressLine2": "achterom",
         "addressZip": "1000 AB", "addressCity": "Stad"},
    ]
    raw["services"] = [{"label": "Rolstoel", "description": "<p>Lift</p>", "isAccessibility": True}]
    out = await queries.cinema_info(CinemasClient([raw]), raw["slug"])
    assert "Zaal Noord: Straat 1, 1000 AA Stad" in out
    assert "Zaal Zuid: Laan 2, achterom, 1000 AB Stad" in out
    assert "PMR" not in out, "hasPmrService is false everywhere, so it is never shown"
    assert "**Rolstoel**  ‹toegankelijkheid›\nLift" in out
    assert "kaart:" not in out


async def test_cinema_info_json(client):
    import json

    got = json.loads(await queries.cinema_info(client, CINEMA, as_json=True))
    assert got["halls"] == 6 and got["seats"] == 1075
    assert "pmr_service" not in got
    assert got["addresses"][0]["postcode"] == "5707 BX"
    assert [s["label"] for s in got["services"]] == ["Parkeren", "Ondersteuning", "Openingstijden"]
    assert "<" not in got["services"][0]["description"]
