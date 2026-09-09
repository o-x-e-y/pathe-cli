"""Offline test rig.

Every test drives `FakeClient`, which serves the recorded fixtures in
`tests/fixtures/`. Those were captured from the live API on 2026-09-09, so the
shapes are real rather than invented -- including the awkward ones the filters
exist for (André Rieu is `nlnl` but not a dub; Toy Story 5 ships as a separate
dubbed show entry).

Nothing here touches the network, and no test depends on today's date.
"""

import json
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# The two dates the showtime fixtures were recorded for. 09-13 is a Sunday and
# 09-14 the Monday after -- the In the Picture pair.
SUNDAY = "2026-09-13"
MONDAY = "2026-09-14"
CINEMA = "pathe-helmond"


def load(name):
    with (FIXTURES / name).open() as handle:
        return json.load(handle)


class FakeClient:
    """Stands in for PatheClient. Counts requests so tests can assert that
    filtering really does happen before the fanout."""

    def __init__(self, missing_showtimes_ok=True):
        self.calls = []
        self.missing_showtimes_ok = missing_showtimes_ok

    async def cinemas(self):
        self.calls.append("cinemas")
        return load("cinemas.json")

    async def shows(self):
        self.calls.append("shows")
        return load("shows.json")

    async def cinema_matrix(self, cinema):
        self.calls.append(f"matrix:{cinema}")
        try:
            return load(f"cinema-{cinema}.json")
        except FileNotFoundError:
            return {"days": {}, "shows": {}}

    async def show_cinemas(self, slug):
        self.calls.append(f"show_cinemas:{slug}")
        try:
            return load(f"show-cinemas/{slug}.json")
        except FileNotFoundError:
            return {}

    async def showtimes(self, show, cinema, date):
        self.calls.append(f"showtimes:{show}:{cinema}:{date}")
        try:
            return load(f"showtimes/{show}__{cinema}__{date}.json")
        except FileNotFoundError:
            if self.missing_showtimes_ok:
                return []
            raise

    async def gather_showtimes(self, triples):
        return {t: await self.showtimes(*t) for t in triples}

    @property
    def showtime_calls(self):
        return [c for c in self.calls if c.startswith("showtimes:")]


@pytest.fixture
def client():
    return FakeClient()


@pytest.fixture
def catalogue():
    from pathe.catalogue import Catalogue

    return Catalogue(load("shows.json"))


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """No test may read the machine's real ~/.config/pathe/settings.json, and
    no test may inherit a PATHE_CINEMAS from the shell that ran pytest."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("PATHE_CINEMAS", raising=False)
