"""The Pathé tag vocabulary, harvested from all 31 NL cinemas.

Showtime tags mix four unrelated axes into one flat list: projection format,
seat type, programme strand, and ticketing. Splitting them here keeps the
renderer from having to know which is which.
"""

# Projection format. This is what "is it 3D/4DX/IMAX" resolves to, and it is a
# property of the *screening*, not the film -- the same title plays 4DX at 11:00
# and regular at 20:00 in the same cinema.
FORMATS = {
    "imax": "IMAX",
    "4dx": "4DX",
    "3d": "3D",
    "screenx": "ScreenX",
    "atmos": "Dolby Atmos",
    "dolby": "Dolby Cinema",
    "LIVE": "Live",
}

# Programme strand. `in-the-picture` is Pathé's arthouse label; `Arthouse`
# appears once in the whole country as a legacy `type` and is folded in here.
STRANDS = {
    "in-the-picture": "In the Picture",
    "Arthouse": "In the Picture",
    "classics": "Classics",
    "pridenight": "Pride Night",
    "ladiesnight": "Ladies Night",
    "horrornight": "Horror Night",
    "sneaknight": "Sneak Night",
    "operaencore": "Opera Encore",
    "opera": "Opera",
    "ballet": "Ballet",
    "theater": "Theater",
    "music": "Music",
    "docs": "Docs",
    "bollywood": "Bollywood",
    "soundsessions": "Sound Sessions",
    "kleuter": "Kleuterbios",
    "50Plus": "50+",
}

# Seat type. Never a reason to pick a screening on its own, so the renderer
# only shows these when nothing else distinguishes a row.
SEATS = {
    "relaxseats": "relaxstoelen",
    "boutiqueseats": "boutiqueseats",
    "luxeseats": "luxeseats",
    "relax-seat-zone": "relaxzone",
    "grotzezaal": "grote zaal",
}

# Ticketing / event dressing. Carried through to the notes column because
# "AVP" (avant-première) and "PAUSE" genuinely change what you are buying.
NOTES = {
    "PAUSE": "met pauze",
    "AVP": "voorpremière",
    "avp": "voorpremière",
    "publiekspremiere": "publiekspremière",
    "Proseccopremière": "proseccopremière",
    "lastchance": "laatste kans",
    "includingQA": "incl. Q&A",
    "debrief": "nabespreking",
    "castbezoek": "castbezoek",
    "rooftop": "rooftop",
    "Bioscoop10Daagse": "Bioscoop10Daagse",
    "bios10d-2voor1": "2-voor-1",
}

# Present on essentially every cell; means "no special format".
FILLER = {"DEFAULT"}

VERSIONS = {"ov": "OV", "nlnl": "NL"}


def _pick(tags, table):
    """Table lookups preserving `table`'s order, so output never reshuffles."""
    present = set(tags)
    return [label for key, label in table.items() if key in present]


def formats(tags):
    return _pick(tags, FORMATS)


def strands(tags):
    # dict.fromkeys dedupes Arthouse/in-the-picture, which both map to one label.
    return list(dict.fromkeys(_pick(tags, STRANDS)))


def seats(tags):
    return _pick(tags, SEATS)


def notes(tags):
    return list(dict.fromkeys(_pick(tags, NOTES)))


def version_label(version):
    return VERSIONS.get(version, version or "")


def unknown(tags):
    """Tags we have no label for -- surfaced by `pathe tags` so the vocabulary
    can be extended when Pathé invents a new strand, rather than silently lost."""
    known = set(FORMATS) | set(STRANDS) | set(SEATS) | set(NOTES) | FILLER
    return sorted(set(tags) - known)
