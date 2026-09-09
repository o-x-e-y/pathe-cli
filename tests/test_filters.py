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
