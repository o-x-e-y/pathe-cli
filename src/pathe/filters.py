"""Default programme filters.

Both rules run against the cinema matrix, before any showtime request is made,
which is what keeps the fanout small. Each filter reports what it removed so the
renderer can print a `gefilterd:` line -- nothing disappears silently.
"""

import datetime as dt
import re
from dataclasses import dataclass, field

# Pathé ships a dub as its own show entry, marked in the title. Checked against
# the full catalogue: this matches 8 titles, all genuine dubs, and none of the
# Dutch-language originals.
#
# Matching on the title and NOT on `version == "nlnl"` is deliberate. André
# Rieu, Golden Earring Live and Maximapark are all nlnl because they are Dutch
# to begin with; a version-based rule would throw them away.
DUB_MARKER = re.compile(
    r"\(\s*(?:NL|Nederlands\s+gesproken|Nederlandse\s+versie)\s*\)",
    re.IGNORECASE,
)


def is_dub(title):
    return bool(DUB_MARKER.search(title or ""))


@dataclass
class Filtered:
    """What a filter pass removed, for the `gefilterd:` line."""

    dubs: list = field(default_factory=list)
    kids: list = field(default_factory=list)
    outside_window: int = 0  # screenings, not titles: the window cuts within a day

    def __bool__(self):
        return bool(self.dubs or self.kids or self.outside_window)

    def summary(self):
        # Deduped: a title filtered at four cinemas is still one title, and
        # listing it four times made the line unreadable.
        dubs = sorted(set(self.dubs))
        kids = sorted(set(self.kids))
        parts = []
        if dubs:
            parts.append(f"{len(dubs)} nagesynchroniseerd ({', '.join(dubs)})")
        if kids:
            noun = "kinderfilm" if len(kids) == 1 else "kinderfilms"
            parts.append(f"{len(kids)} {noun} ({', '.join(kids)})")
        if self.outside_window:
            noun = "voorstelling" if self.outside_window == 1 else "voorstellingen"
            parts.append(f"{self.outside_window} {noun} buiten het tijdvenster")
        return "gefilterd: " + "; ".join(parts) if parts else ""

def apply(entries, *, include_dubs=False, include_kids=False):
    """Split `entries` into (kept, Filtered).

    An entry is any object with `.title` and `.is_kids`. A title can be both a
    dub and a kids film; it is reported once, under the dub heading, so the
    counts in the summary add up to the number of titles actually removed.
    """
    kept, dropped = [], Filtered()
    for e in entries:
        if not include_dubs and is_dub(e.title):
            dropped.dubs.append(e.title)
        elif not include_kids and e.is_kids:
            dropped.kids.append(e.title)
        else:
            kept.append(e)
    return kept, dropped


def window(cells, *, starts_after=None, ends_before=None):
    """Drop the screenings outside the time window, in place, and return how
    many went.

    Both bounds are `timedelta`s after midnight of the cell's own date and are
    inclusive. Measured on full datetimes, so a 22:00 screening ending 00:40 is
    past any `ends_before` that day, and one with no known end cannot meet one.
    Times come from showtimes, so this runs after the fanout, not before it.
    """
    if starts_after is None and ends_before is None:
        return 0
    removed = 0
    for cell in cells:
        midnight = dt.datetime.fromisoformat(cell.date)
        kept = [
            s for s in cell.screenings
            if (starts_after is None or (s.starts_at and s.starts_at >= midnight + starts_after))
            and (ends_before is None or (s.ends_at and s.ends_at <= midnight + ends_before))
        ]
        removed += len(cell.screenings) - len(kept)
        cell.screenings = kept
    return removed
