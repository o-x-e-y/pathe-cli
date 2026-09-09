"""CLI surface: parsing, aliases, filter flags, and main() end to end."""

import datetime as dt

import pytest
from conftest import SUNDAY, FakeClient

from pathe import cli

# ---------------------------------------------------------------- date parsing

def test_iso_date_passes_through():
    assert cli._parse_date("2026-09-13") == "2026-09-13"


def test_today_and_tomorrow():
    today = dt.date.today()
    assert cli._parse_date("today") == today.isoformat()
    assert cli._parse_date("vandaag") == today.isoformat()
    assert cli._parse_date("tomorrow") == (today + dt.timedelta(days=1)).isoformat()
    assert cli._parse_date("morgen") == (today + dt.timedelta(days=1)).isoformat()


def test_relative_offset():
    expected = (dt.date.today() + dt.timedelta(days=5)).isoformat()
    assert cli._parse_date("+5") == expected


def test_empty_means_today():
    assert cli._parse_date(None) == dt.date.today().isoformat()


def test_bad_date_is_rejected_with_a_useful_message():
    import argparse

    with pytest.raises(argparse.ArgumentTypeError) as exc:
        cli._parse_date("13-09-2026")
    assert "JJJJ-MM-DD" in str(exc.value)


# ------------------------------------------------------------------- arg parse

def test_parser_defaults():
    args = cli.parse_args(["programme"])
    assert args.command == "programme" and args.date == "today"
    assert not args.include_dubs and not args.include_kids and not args.all


def test_help_documents_the_strands(capsys):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["--help"])
    out = capsys.readouterr().out
    # An agent reading --help must be able to learn the vocabulary from it.
    for expected in ("in-the-picture", "pridenight", "classics", "gefilterd:", "PATHE_CINEMAS"):
        assert expected in out


def test_help_explains_the_dub_rule(capsys):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["--help"])
    out = capsys.readouterr().out
    assert "Nederlands gesproken" in out
    assert "André Rieu" in out, "the why behind the title-based rule is documented"


def test_no_command_prints_help_and_fails():
    assert cli.main([]) == 1


# ----------------------------------------------------------------- end to end

@pytest.fixture
def fake(monkeypatch):
    """Swap the real client for the fixture-backed one, keeping main() intact."""
    created = []

    class Ctx(FakeClient):
        async def __aenter__(self):
            created.append(self)
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(cli, "PatheClient", lambda **kw: Ctx())
    return created


def run(argv, capsys):
    code = cli.main(argv)
    return code, capsys.readouterr().out


def test_cinemas_command(fake, capsys):
    code, out = run(["cinemas"], capsys)
    assert code == 0 and "pathe-helmond" in out


def test_programme_command(fake, capsys):
    code, out = run(["programme", SUNDAY, "-c", "helmond"], capsys)
    assert code == 0
    assert "zondag 13 september 2026" in out


def test_programme_filters_by_default(fake, capsys):
    _, filtered = run(["programme", SUNDAY, "-c", "helmond"], capsys)
    _, everything = run(["programme", SUNDAY, "-c", "helmond", "--all"], capsys)
    assert "gefilterd:" in filtered
    assert "gefilterd:" not in everything


def test_include_flags_are_independent(fake, capsys):
    _, dubs = run(["programme", SUNDAY, "-c", "helmond", "--include-dubs"], capsys)
    _, kids = run(["programme", SUNDAY, "-c", "helmond", "--include-kids"], capsys)
    assert dubs != kids


def test_arthouse_alias_maps_to_in_the_picture(fake, capsys):
    code, out = run(["arthouse", "-c", "helmond", "--days", "7", "--from", SUNDAY], capsys)
    assert code == 0 and "In the Picture" in out


def test_pride_alias(fake, capsys):
    code, out = run(["pride", "-c", "helmond", "--days", "3", "--from", SUNDAY], capsys)
    assert code == 0 and "Pride Night" in out


def test_classics_alias(fake, capsys):
    code, out = run(["classics", "-c", "helmond", "--days", "3", "--from", SUNDAY], capsys)
    assert code == 0 and "Classics" in out


def test_tagged_accepts_a_friendly_alias(fake, capsys):
    code, out = run(["tagged", "arthouse", "-c", "helmond", "--days", "3", "--from", SUNDAY], capsys)
    assert code == 0 and "In the Picture" in out


def test_tagged_accepts_a_raw_tag(fake, capsys):
    code, out = run(["tagged", "ladiesnight", "-c", "helmond", "--days", "3", "--from", SUNDAY], capsys)
    assert code == 0 and "Ladies Night" in out


def test_film_command(fake, capsys):
    code, out = run(["film", "fuori", "-c", "helmond", "--days", "3", "--from", SUNDAY], capsys)
    assert code == 0 and out.startswith("# ")


def test_upcoming_command(fake, capsys):
    code, out = run(["upcoming", "--limit", "5"], capsys)
    assert code == 0 and "Binnenkort" in out


def test_search_command(fake, capsys):
    code, out = run(["search", "dune"], capsys)
    assert code == 0 and "Dune" in out


def test_unknown_cinema_exits_with_an_error(fake, capsys):
    code = cli.main(["programme", "-c", "atlantis"])
    assert code == 2


def test_multiple_cinemas_via_comma(fake, capsys):
    code, out = run(["programme", SUNDAY, "-c", "helmond,eindhoven"], capsys)
    assert code == 0 and out.count("## ") == 2


def test_cinema_free_commands_skip_slug_resolution(fake, capsys):
    """`upcoming` must not require or fetch the cinema list."""
    run(["upcoming", "--limit", "2"], capsys)
    assert "cinemas" not in fake[0].calls


def test_output_ends_with_newline(fake, capsys):
    _, out = run(["upcoming", "--limit", "2"], capsys)
    assert out.endswith("\n")


def test_global_flags_work_on_either_side_of_the_subcommand(fake, capsys):
    """Regression: the flags were originally top-level only, so the natural
    `pathe programme -c helmond` was rejected as an unrecognised argument."""
    _, before = run(["-c", "helmond", "programme", SUNDAY], capsys)
    _, after = run(["programme", SUNDAY, "-c", "helmond"], capsys)
    assert before == after


def test_flag_before_subcommand_is_not_clobbered_by_the_default(fake, capsys):
    """argparse's parents+subparser trap: without SUPPRESS the subparser's own
    default would silently overwrite a value given before the subcommand."""
    _, out = run(["--all", "programme", SUNDAY, "-c", "helmond"], capsys)
    assert "gefilterd:" not in out


def test_days_flag_widens_the_window(fake, capsys):
    _, narrow = run(["arthouse", "-c", "helmond", "--days", "1", "--from", SUNDAY], capsys)
    _, wide = run(["arthouse", "-c", "helmond", "--days", "14", "--from", SUNDAY], capsys)
    assert len(wide) > len(narrow)
