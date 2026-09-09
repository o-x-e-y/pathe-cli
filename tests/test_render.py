"""Rendering. The determinism tests here are the whole point of formatting
server-side rather than handing raw JSON to a model to lay out."""

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
