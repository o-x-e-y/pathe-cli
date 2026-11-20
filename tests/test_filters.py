"""The dub and kids rules -- the part most likely to quietly do the wrong thing."""

import pytest
from conftest import load

from pathe import filters


class Entry:
    def __init__(self, title, is_kids=False):
        self.title = title
        self.is_kids = is_kids


@pytest.mark.parametrize(
    "title",
    [
        "Minions & Monsters (NL)",
        "Toy Story 5 (Nederlandse versie)",
        "Paw Patrol: De Dinofilm (Nederlands gesproken)",
        "Vaiana (2026) (Nederlands gesproken)",
        "Hotel Transylvania (NL) (2012)",
        "The Cat in the Hat (NL)",
        "Disney's Hexed (NL)",
        "Het Vergeten Eiland (Nederlandse versie)",
        "iets (  Nederlands   gesproken  )",  # tolerant of stray whitespace
        "iets (nl)",                           # and of case
    ],
)
def test_recognises_dubs(title):
    assert filters.is_dub(title)


@pytest.mark.parametrize(
    "title",
    [
        # Dutch-language, but originals rather than dubs. A rule keyed on the
        # `nlnl` version code instead of the title would wrongly drop all four.
        "André Rieu's 2026 Christmas Concert: Let It Snow",
        "Golden Earring Live",
        "Maximapark",
        "F*ck de Familie",
        # Near-misses that must not trip the marker.
        "The Netherlands",
        "Nederland in beweging",
        "Forgotten Island",
        "Spider-Man: Brand New Day",
        "",
    ],
)
def test_keeps_non_dubs(title):
    assert not filters.is_dub(title)


def test_is_dub_handles_none():
    assert not filters.is_dub(None)


def test_apply_splits_and_reports():
    entries = [
        Entry("Spider-Man: Brand New Day"),
        Entry("Toy Story 5 (Nederlandse versie)", is_kids=True),
        Entry("Bumba: Het Circusorkest", is_kids=True),
        Entry("Fuori"),
    ]
    kept, dropped = filters.apply(entries)
    assert [e.title for e in kept] == ["Spider-Man: Brand New Day", "Fuori"]
    assert dropped.dubs == ["Toy Story 5 (Nederlandse versie)"]
    assert dropped.kids == ["Bumba: Het Circusorkest"]


def test_dub_and_kids_counted_once():
    """Toy Story 5 is both. It must appear under one heading only, or the
    counts in the summary stop matching the number of titles removed."""
    kept, dropped = filters.apply([Entry("Toy Story 5 (Nederlandse versie)", is_kids=True)])
    assert kept == []
    assert len(dropped.dubs) == 1
    assert dropped.kids == []


def test_include_flags_disable_each_rule():
    """The two rules are independent, and a title caught by both needs both
    flags to survive -- Toy Story 5 is a dub *and* a kids film."""
    both = Entry("Toy Story 5 (Nederlandse versie)", is_kids=True)
    kids_only = Entry("Bumba", is_kids=True)
    dub_only = Entry("Hotel Transylvania (NL) (2012)", is_kids=False)
    entries = [both, kids_only, dub_only]

    # Dubs allowed back, kids still filtered: only the non-kids dub returns.
    kept, _ = filters.apply(entries, include_dubs=True)
    assert [e.title for e in kept] == ["Hotel Transylvania (NL) (2012)"]

    # Kids allowed back, dubs still filtered: only the non-dub kids film returns.
    kept, _ = filters.apply(entries, include_kids=True)
    assert [e.title for e in kept] == ["Bumba"]

    kept, dropped = filters.apply(entries, include_dubs=True, include_kids=True)
    assert len(kept) == 3
    assert not dropped
def test_summary_is_empty_when_nothing_dropped():
    _, dropped = filters.apply([Entry("Fuori")])
    assert not dropped
    assert dropped.summary() == ""


def test_summary_names_what_went():
    _, dropped = filters.apply([Entry("Toy Story 5 (NL)"), Entry("Bumba", is_kids=True)])
    summary = dropped.summary()
    assert summary.startswith("gefilterd:")
    assert "Toy Story 5 (NL)" in summary
    assert "Bumba" in summary
    assert "1 kinderfilm (" in summary  # singular


def test_summary_pluralises_kids():
    _, dropped = filters.apply([Entry("A", is_kids=True), Entry("B", is_kids=True)])
    assert "2 kinderfilms" in dropped.summary()


def test_every_catalogue_dub_is_caught():
    """Against the real catalogue: the marker must catch exactly the eight
    dubbed entries and nothing else."""
    titles = [s["title"] for s in load("shows.json")["shows"]]
    flagged = sorted(t for t in titles if filters.is_dub(t))
    assert flagged == sorted([
        "Disney's Hexed (NL)",
        "Het Vergeten Eiland (Nederlandse versie)",
        "Hotel Transylvania (NL) (2012)",
        "Minions & Monsters (NL)",
        "Paw Patrol: De Dinofilm (Nederlands gesproken)",
        "The Cat in the Hat (NL)",
        "Toy Story 5 (Nederlandse versie)",
        "Vaiana (2026) (Nederlands gesproken)",
    ])


def test_summary_dedupes_across_cinemas():
    """A title filtered at four cinemas is one title, not four. Without this
    the note runs to several unreadable lines on a multi-cinema query."""
    dropped = filters.Filtered(dubs=["Toy Story 5 (NL)"] * 4, kids=["Bumba"] * 3)
    summary = dropped.summary()
    assert summary.count("Toy Story 5 (NL)") == 1
    assert summary.startswith("gefilterd: 1 nagesynchroniseerd")
    assert "1 kinderfilm (Bumba)" in summary


# ----------------------------------------------------------------- time window

def _cell(*spans, date="2026-09-13"):
    """A cell whose screenings run over `spans` of (start, end) datetimes."""
    import datetime as dt

    from pathe.catalogue import Cell, Film, Screening

    def at(text):
        return dt.datetime.fromisoformat(text) if text else None

    screenings = [
        Screening(start=s[11:16], end=(e or "")[11:16], formats=(), version="", hall="",
                  notes=(), status="", starts_at=at(s), ends_at=at(e))
        for s, e in spans
    ]
    return Cell(date=date, cinema="c", film=Film(slug="x-1", title="X"), screenings=screenings)


def _hm(text):
    import datetime as dt

    hours, minutes = text.split(":")
    return dt.timedelta(hours=int(hours), minutes=int(minutes))


EVENING = ("2026-09-13 19:00", "2026-09-13 21:00")
LATE = ("2026-09-13 22:00", "2026-09-14 00:40")


@pytest.mark.parametrize("bounds, kept", [
    ({"starts_after": "19:00"}, 1),
    ({"starts_after": "19:01"}, 0),
    ({"ends_before": "21:00"}, 1),
    ({"ends_before": "20:59"}, 0),
])
def test_window_bounds_are_inclusive(bounds, kept):
    cell = _cell(EVENING)
    removed = filters.window([cell], **{k: _hm(v) for k, v in bounds.items()})
    assert len(cell.screenings) == kept and removed == 1 - kept


@pytest.mark.parametrize("ends_before", ["23:30", "24:00"])
def test_a_screening_ending_after_midnight_fails_ends_before(ends_before):
    """22:00-00:40 ends tomorrow. Compared on HH:MM alone it would look like it
    ends at 00:40 today and pass any limit."""
    cell = _cell(LATE)
    assert filters.window([cell], ends_before=_hm(ends_before)) == 1
    assert cell.screenings == []


def test_both_bounds_together():
    early = ("2026-09-13 13:00", "2026-09-13 15:00")
    cell = _cell(early, EVENING, LATE)
    removed = filters.window([cell], starts_after=_hm("18:00"), ends_before=_hm("23:00"))
    assert removed == 2
    assert [s.start for s in cell.screenings] == ["19:00"]


def test_no_end_time_cannot_meet_ends_before():
    cell = _cell(("2026-09-13 19:00", None))
    assert filters.window([cell], starts_after=_hm("18:00")) == 0
    assert filters.window([cell], ends_before=_hm("23:59")) == 1


def test_no_window_leaves_everything():
    cell = _cell(EVENING, LATE)
    assert filters.window([cell]) == 0
    assert len(cell.screenings) == 2


def test_window_is_relative_to_the_cells_own_date():
    """A screening listed under the 13th that starts at 00:30 on the 14th is
    still after 22:00 *that evening*."""
    cell = _cell(("2026-09-14 00:30", "2026-09-14 02:30"))
    assert filters.window([cell], starts_after=_hm("22:00")) == 0


def test_the_window_count_alone_makes_filtered_truthy():
    """Nothing disappears silently: a window-only drop still prints the line."""
    assert filters.Filtered(outside_window=1)
    assert filters.Filtered(outside_window=1).summary() == (
        "gefilterd: 1 voorstelling buiten het tijdvenster"
    )
    assert filters.Filtered(outside_window=12).summary().endswith(
        "12 voorstellingen buiten het tijdvenster"
    )


def test_the_window_count_follows_the_title_filters():
    dropped = filters.Filtered(dubs=["A (NL)"], outside_window=3)
    assert dropped.summary() == (
        "gefilterd: 1 nagesynchroniseerd (A (NL)); 3 voorstellingen buiten het tijdvenster"
    )
