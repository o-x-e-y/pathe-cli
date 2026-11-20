"""Rendering. The determinism tests here are the whole point of formatting
server-side rather than handing raw JSON to a model to lay out."""

import pytest
from conftest import load

from pathe import render
from pathe.catalogue import Film, parse_screenings


def film(**kw):
    base = {"slug": "x-1", "title": "Testfilm", "duration": 100, "genres": ("Drama",), "rating": "-12 jaar"}
    base.update(kw)
    return Film(**base)


def test_dutch_date_names_the_weekday():
    # The weekday is load-bearing: In the Picture is a Sunday/Monday strand and
    # Pride Night is a Wednesday, so a bare date hides the pattern.
    assert render.dutch_date("2026-09-13") == "zondag 13 september 2026"
    assert render.dutch_date("2026-09-14") == "maandag 14 september 2026"
    assert render.dutch_date("2026-10-07") == "woensdag 7 oktober 2026"


def test_dutch_date_passes_through_garbage():
    assert render.dutch_date("niet-een-datum") == "niet-een-datum"
    assert render.dutch_date(None) is None


def test_film_line_leads_with_runtime():
    """The user's requirement: length and format at the top of every film."""
    line = render.film_line(film(), formats=["IMAX", "3D"], version="OV")
    assert line.startswith("100 min")
    assert line == "100 min · IMAX, 3D · -12 jaar · OV · Drama"


def test_film_line_omits_empty_parts():
    line = render.film_line(Film(slug="a-1", title="A"))
    assert line == "duur onbekend"


def test_screening_rows_align_columns():
    rows = render.screening_rows(parse_screenings(load("showtimes-spider-arena.json")))
    # Every row's format column starts at the same offset, so the block reads
    # as a table when pasted into a plain-text context.
    assert len(rows) > 1
    assert all(row.startswith("  ") for row in rows)
    assert len({len(row.split("  ")[1]) for row in rows}) == 1


def test_screening_row_marks_a_plain_screening():
    rows = render.screening_rows(parse_screenings(load("showtimes-spider-arena.json")))
    assert any(render.NO_FORMAT in row for row in rows), "flat 2D screenings show a dash"


def test_screening_rows_empty():
    assert render.screening_rows([]) == []


def test_section_reports_emptiness_rather_than_vanishing():
    out = render.section("Pathé Helmond", [])
    assert "Geen voorstellingen gevonden" in out


def test_section_appends_the_filter_note():
    out = render.section("H", ["**A**"], note="gefilterd: 1 kinderfilm (Bumba)")
    assert out.endswith("_gefilterd: 1 kinderfilm (Bumba)_")


def test_document_is_stable_across_calls():
    """Same input twice, byte-identical output. This is the property that lets
    output be pasted somewhere without drifting between runs."""
    screenings = parse_screenings(load("showtimes-spider-arena.json"))
    build = lambda: render.document([render.section("H", ["\n".join(render.screening_rows(screenings))])])
    assert build() == build()


def test_document_ends_with_exactly_one_newline():
    out = render.document([render.section("H", ["**A**"])])
    assert out.endswith("\n") and not out.endswith("\n\n")


def test_cell_block_puts_metadata_under_the_title():
    class Cell:
        title = "Spider-Man: Brand New Day"
        film = film(title="Spider-Man: Brand New Day", duration=145)
        strands = ["Classics"]
        screenings = parse_screenings(load("showtimes-spider-arena.json"))

    block = render.cell_block(Cell())
    lines = block.splitlines()
    assert lines[0] == "**Spider-Man: Brand New Day**  ‹Classics›"
    assert lines[1].startswith("145 min · ")
    assert lines[2].startswith("  ")


def test_cell_block_format_union_is_ordered():
    """The header lists every format the day offers, in table order, so it does
    not reshuffle when the API returns screenings in a different sequence."""
    class Cell:
        title = "T"
        film = film(duration=145)
        strands = []
        screenings = parse_screenings(load("showtimes-spider-arena.json"))

    line = render.cell_block(Cell()).splitlines()[1]
    assert "4DX, 3D" in line


def test_short_date():
    from pathe import render

    assert render.short_date("2026-09-16") == "wo 16 sep"
    assert render.short_date("2026-03-01") == "zo 1 mrt"
    assert render.short_date("nonsense") == "nonsense"


def test_date_span_of_a_single_day():
    from pathe import render

    assert render.date_span(["2026-09-09"]) == "wo 9 sep"


def test_date_span_of_a_full_run():
    from pathe import render

    days = [f"2026-09-{d:02d}" for d in range(9, 17)]
    assert render.date_span(days) == "wo 9 sep – wo 16 sep"


def test_date_span_counts_days_when_the_run_has_gaps():
    """A bare span would claim Zwolle plays it every day between the ends; it
    plays five of those seven."""
    from pathe import render

    days = ["2026-09-09", "2026-09-10", "2026-09-12", "2026-09-14", "2026-09-15"]
    assert render.date_span(days) == "wo 9 sep – di 15 sep (5 dagen)"


def test_cinema_rows_align_the_spans():
    from pathe import render

    rows = render.cinema_rows([
        ("pathe-arena", "Pathé Arena", ["2026-09-09"]),
        ("pathe-zwolle", "Pathé Zwolle Lang", ["2026-09-09"]),
    ])
    assert rows[0] == "  `pathe-arena`\n     Pathé Arena        wo 9 sep"
    assert rows[1] == "  `pathe-zwolle`\n     Pathé Zwolle Lang  wo 9 sep"


def test_cinema_rows_of_nothing():
    from pathe import render

    assert render.cinema_rows([]) == []


def test_links_add_an_aligned_bare_url_column():
    rows = render.screening_rows(parse_screenings(load("showtimes-spider-arena.json")), links=True)
    starts = {row.index("https://") for row in rows}
    assert len(starts) == 1, "every URL starts in the same column"
    assert all(row.split()[-1].startswith("https://s.pathe.nl/") for row in rows)
    assert "](" not in "".join(rows), "a plain URL, not Markdown link syntax"


def test_links_off_is_the_old_layout():
    screenings = parse_screenings(load("showtimes-spider-arena.json"))
    rows = render.screening_rows(screenings)
    assert rows == render.screening_rows(screenings, links=False)
    assert "https://" not in "".join(rows)


def test_a_screening_without_a_url_gets_no_link():
    screenings = parse_screenings([
        {"time": "2026-09-13 19:00:00", "endTime": "2026-09-13 21:00:00",
         "auditoriumName": "1", "refCmd": "https://s.pathe.nl/a"},
        {"time": "2026-09-13 21:30:00", "endTime": "2026-09-13 23:30:00",
         "auditoriumName": "1"},
    ])
    with_link, without = render.screening_rows(screenings, links=True)
    assert with_link.endswith("https://s.pathe.nl/a")
    assert without == "  21:30–23:30  —  zaal 1"


def test_plain_text_strips_markup():
    markup = "<p><strong>Adres</strong>&nbsp;Steenweg 1<br />\r\nTarief &euro; 2,50</p><p>&nbsp;</p>"
    assert render.plain_text(markup) == "Adres: Steenweg 1\nTarief € 2,50"
    assert render.plain_text(None) == ""


def test_json_conventions():
    out = render.to_json({"name": "Pathé", "films": []})
    assert out == '{\n  "name": "Pathé",\n  "films": []\n}\n'


def test_screening_json_keeps_dates_and_nulls_a_missing_link():
    (late,) = parse_screenings([
        {"time": "2026-09-13 22:00:00", "endTime": "2026-09-14 00:40:00"},
    ])
    got = render.screening_json(late)
    assert got["date"] == "2026-09-13"
    assert got["start"] == "2026-09-13T22:00"
    assert got["end"] == "2026-09-14T00:40"
    assert got["booking_url"] is None
    assert list(got) == ["date", "start", "end", "hall", "formats", "version", "notes",
                         "booking_url"]


def test_film_json_shape():
    got = render.film_json(film(directors=("A", "B"), strand="Classics"))
    assert got == {
        "slug": "x-1", "title": "Testfilm", "runtime_min": 100, "rating": "-12 jaar",
        "genres": ["Drama"], "directors": ["A", "B"], "strands": ["Classics"],
        "release": None, "coming_soon": False,
    }
    assert render.film_json(Film(slug="a-1", title="A"))["runtime_min"] is None


def test_plain_text_keeps_a_label_apart_from_its_text():
    """Helmond's real Parkeren HTML: the bold heading and the sentence after it
    are separated only by `&nbsp;`, so dropping the tags glued them together."""
    helmond = next(c for c in load("cinemas.json") if c["slug"] == "pathe-helmond")
    parking, support, _ = (s["description"] for s in helmond["services"])
    assert render.plain_text(parking).splitlines() == [
        ("1. Parkeergarage Boscotondo: Het tarief is € 2,50 per uur."
         " Het dagtarief is € 15,50 per dag."),
        ("Gehandicaptenparkeerplaats: De dichtstbijzijnde gehandicaptenparkeerplaats vind je op"
         " het Frans Jospeh van Thielpark."),
        "Adres: Frans Joseph van Thielpark 1",
        "Tarief: € 2,50",
        ("2. Parkeerplaats Hotel West Ende: Het tarief voor het parkeren bedraagt € 2,- per uur"
         " (of 4 uur gratis bij deelname Filmdiner)."),
        "Adres: Steenweg 1",
    ]
    lines = render.plain_text(support).splitlines()
    assert lines[:2] == [
        "Rolstoelmogelijkheden",
        ("Alle zalen zijn rolstoeltoegankelijk en gelijkvloers (via lift) te bereiken."
         " Rolstoelvriendelijk toilet aanwezig."),
    ], "a heading already on its own line stays there"
    assert "Binnen 48 uur worden gevonden voorwerpen op ILost.co gezet." in lines, (
        "bold or linked words inside a sentence stay inline"
    )


@pytest.mark.parametrize("markup, expected", [
    ("<p><strong>3.</strong><strong>P+R Noord</strong>&nbsp;Vanaf hier</p>", "3. P+R Noord: Vanaf hier"),
    ("<p><strong>Plaats</strong>:&nbsp;De dichtstbijzijnde</p>", "Plaats: De dichtstbijzijnde"),
    ("<p><strong>Plaats</strong><strong>:</strong>&nbsp;De</p>", "Plaats: De"),
    ("<p><strong>Plek vinden?</strong>&nbsp;Kijk hier</p>", "Plek vinden? Kijk hier"),
    ("<p><strong>Gratis</strong></p>", "Gratis"),
])
def test_plain_text_label_edge_cases(markup, expected):
    assert render.plain_text(markup) == expected
