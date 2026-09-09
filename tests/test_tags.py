"""Tag vocabulary. The ordering guarantees here are what make output stable."""

from conftest import load

from pathe import tags


def test_splits_the_four_axes():
    raw = ["DEFAULT", "3d", "4dx", "relaxseats", "classics", "PAUSE"]
    assert tags.formats(raw) == ["4DX", "3D"]
    assert tags.strands(raw) == ["Classics"]
    assert tags.seats(raw) == ["relaxstoelen"]
    assert tags.notes(raw) == ["met pauze"]


def test_format_order_is_table_order_not_input_order():
    """Two different orderings of the same tags must render identically, or
    the same query run twice produces different bytes."""
    assert tags.formats(["3d", "imax", "4dx"]) == tags.formats(["4dx", "3d", "imax"])
    assert tags.formats(["3d", "imax", "4dx"]) == ["IMAX", "4DX", "3D"]


def test_arthouse_and_in_the_picture_collapse_to_one_label():
    assert tags.strands(["in-the-picture"]) == ["In the Picture"]
    assert tags.strands(["Arthouse"]) == ["In the Picture"]
    assert tags.strands(["Arthouse", "in-the-picture"]) == ["In the Picture"]


def test_default_is_not_a_format():
    assert tags.formats(["DEFAULT"]) == []
    assert tags.unknown(["DEFAULT"]) == []


def test_versions():
    assert tags.version_label("ov") == "OV"
    assert tags.version_label("nlnl") == "NL"
    assert tags.version_label(None) == ""
    assert tags.version_label("xx") == "xx"


def test_duplicate_note_tags_collapse():
    # AVP and avp both appear in the wild and mean the same thing.
    assert tags.notes(["AVP", "avp"]) == ["voorpremière"]


def test_unknown_surfaces_only_unmapped():
    assert tags.unknown(["imax", "DEFAULT", "vrgoggles"]) == ["vrgoggles"]


def test_whole_national_vocabulary_is_mapped():
    """Every tag present across all 31 cinemas on the recorded day has a label.
    A new Pathé strand should fail here rather than render as a raw slug."""
    seen = set()
    matrix = load("cinema-pathe-helmond.json")
    for node in matrix["shows"].values():
        for cell in node["days"].values():
            seen.update(cell.get("tags") or ())
    assert tags.unknown(seen) == []


def test_empty_input_is_safe():
    assert tags.formats([]) == tags.strands([]) == tags.seats([]) == tags.notes([]) == []
