"""Domain model over the two catalogue endpoints.

`/api/shows` gives per-title metadata but no dates; `/api/cinema/X/shows` gives
dates but no metadata. Neither is useful alone, so this module joins them on
the show slug and hands out `Cell`s: one title, at one cinema, on one date.
"""

import datetime as dt
import unicodedata
from dataclasses import dataclass, field

from . import tags as tagmod


@dataclass(frozen=True)
class Film:
    slug: str
    title: str
    duration: int | None = None
    genres: tuple = ()
    rating: str = ""
    directors: tuple = ()
    strand: str = ""       # `type` in the API: Classics, Ballet, Music, ...
    label: str = ""        # `label`: e.g. "In The Picture"
    release: str = ""
    coming_soon: bool = False
    upcoming_order: int | None = None

    @property
    def runtime(self):
        return f"{self.duration} min" if self.duration else "duur onbekend"


@dataclass
class Cell:
    """One (film, cinema, date) that Pathé says exists, before showtimes are fetched."""

    date: str
    cinema: str
    film: Film
    tags: tuple = ()
    versions: tuple = ()
    flag: str = ""
    is_kids: bool = False
    screenings: list = field(default_factory=list)

    @property
    def title(self):
        return self.film.title

    @property
    def strands(self):
        merged = list(self.tags)
        if self.film.strand:
            merged.append(self.film.strand)
        return tagmod.strands(merged)


@dataclass
class Screening:
    start: str
    end: str
    formats: tuple
    version: str
    hall: str
    notes: tuple
    status: str


def _fold(text):
    """Accent- and case-insensitive key for title search."""
    stripped = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in stripped if not unicodedata.combining(c)).casefold()


class Catalogue:
    """The national title index, keyed by slug."""

    def __init__(self, shows_payload):
        self.films = {}
        for raw in shows_payload.get("shows", []):
            film = Film(
                slug=raw["slug"],
                title=raw.get("title") or raw["slug"],
                duration=raw.get("duration"),
                genres=tuple(raw.get("genres") or ()),
                rating=(raw.get("contentRating") or {}).get("description", ""),
                directors=tuple(raw.get("directors") or ()),
                strand=raw.get("type") or "",
                label=raw.get("label") or "",
                release=(raw.get("releaseAt") or {}).get("NL_NL", ""),
                coming_soon=bool(raw.get("isComingSoon")),
                upcoming_order=raw.get("upcomingOrder"),
            )
            self.films[film.slug] = film

    def get(self, slug):
        """Films that are only in a cinema matrix (rare, mostly one-off events)
        are not in the national catalogue; synthesise a stub from the slug so
        they still render instead of vanishing."""
        if slug in self.films:
            return self.films[slug]
        pretty = slug.rsplit("-", 1)[0].replace("-", " ").title()
        return Film(slug=slug, title=pretty)

    def search(self, query):
        """Substring match on title, then slug. Exact title first, then
        shortest match, so `dune` finds the film and not a making-of."""
        needle = _fold(query)
        hits = [f for f in self.films.values() if needle in _fold(f.title) or needle in f.slug]
        return sorted(hits, key=lambda f: (_fold(f.title) != needle, len(f.title), f.title))

    def upcoming(self):
        pending = [f for f in self.films.values() if f.coming_soon]
        return sorted(
            pending,
            key=lambda f: (f.upcoming_order is None, f.upcoming_order or 0, f.release or "9999"),
        )


def date_range(days, start=None):
    first = start or dt.date.today()
    return [(first + dt.timedelta(days=i)).isoformat() for i in range(days)]


def cells(matrix, cinema, catalogue, dates):
    """Every (film, date) the matrix lists for `cinema` inside `dates`.

    This is the whole reason the fanout stays small: one matrix request covers
    the full horizon and tells us exactly which cells exist, so no date is ever
    blind-polled.
    """
    wanted = set(dates)
    out = []
    for slug, node in (matrix.get("shows") or {}).items():
        film = catalogue.get(slug)
        for date, cell in (node.get("days") or {}).items():
            if date not in wanted:
                continue
            out.append(
                Cell(
                    date=date,
                    cinema=cinema,
                    film=film,
                    tags=tuple(cell.get("tags") or ()),
                    versions=tuple(cell.get("versions") or ()),
                    flag=cell.get("flag") or "",
                    is_kids=bool(node.get("isKids")),
                )
            )
    out.sort(key=lambda c: (c.date, c.film.title))
    return out


def playing_dates(payload, dates):
    """`{cinema: [date, ...]}` from `/show/{slug}/cinemas`, inside `dates`.

    Cinemas with nothing in the window drop out entirely, so the caller can
    take `len()` of the result as "how many cinemas have it".
    """
    wanted = set(dates)
    out = {}
    for cinema, node in (payload or {}).items():
        days = sorted(d for d in (node.get("days") or {}) if d in wanted)
        if days:
            out[cinema] = days
    return out


def parse_screenings(payload):
    out = []
    for raw in payload or []:
        combined = tuple(raw.get("tags") or ())
        out.append(
            Screening(
                start=(raw.get("time") or "")[11:16],
                end=(raw.get("endTime") or "")[11:16],
                formats=tuple(tagmod.formats(combined)),
                version=tagmod.version_label(raw.get("version")),
                hall=raw.get("auditoriumName") or "",
                notes=tuple(tagmod.notes(combined)),
                status=raw.get("status") or "",
            )
        )
    out.sort(key=lambda s: s.start)
    return out
