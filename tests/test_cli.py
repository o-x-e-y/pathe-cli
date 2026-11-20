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


@pytest.mark.parametrize("value, today, expected", [
    ("20", "2026-10-05", "2026-10-20"),
    ("5", "2026-10-05", "2026-10-05"),
    ("08", "2026-10-19", "2026-11-08"),
    ("3", "2026-12-19", "2027-01-03"),
    ("11-01", "2026-10-05", "2026-11-01"),
    ("10-05", "2026-10-05", "2026-10-05"),
    ("01-15", "2026-11-20", "2027-01-15"),
    ("1-5", "2026-11-20", "2027-01-05"),
])
def test_short_dates_mean_the_next_such_date(value, today, expected):
    assert cli._parse_date(value, dt.date.fromisoformat(today)) == expected


@pytest.mark.parametrize("value, today", [
    ("31", "2026-11-05"),
    ("30", "2026-01-31"),
    ("02-30", "2026-01-01"),
    ("13-09", "2026-01-01"),
])
def test_short_dates_that_do_not_exist_are_rejected(value, today):
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        cli._parse_date(value, dt.date.fromisoformat(today))


@pytest.mark.parametrize("value, hint", [
    ("31-10", "bedoel je 2026-10-31?"),
    ("13-09-2026", "bedoel je 2026-09-13?"),
])
def test_day_month_order_gets_a_suggestion(value, hint):
    import argparse

    with pytest.raises(argparse.ArgumentTypeError) as exc:
        cli._parse_date(value, dt.date(2026, 10, 5))
    assert str(exc.value).endswith(hint)


def test_no_suggestion_when_neither_order_is_a_date():
    import argparse

    with pytest.raises(argparse.ArgumentTypeError) as exc:
        cli._parse_date("02-30", dt.date(2026, 10, 5))
    assert "bedoel je" not in str(exc.value)


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


def test_bad_date_is_an_error_message_not_a_traceback(fake, capsys):
    assert cli.main(["programme", "31-10", "-c", "helmond"]) == 2
    assert "onbegrijpelijke datum" in capsys.readouterr().err


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


def test_favorites_flag_parses_on_either_side():
    """The SUPPRESS trap CLAUDE.md documents: a flag given before the
    subcommand must survive the subparser's own parse."""
    assert cli.parse_args(["-f", "where", "dune"]).favorites is True
    assert cli.parse_args(["where", "dune", "-f"]).favorites is True
    assert cli.parse_args(["where", "dune"]).favorites is False


def test_where_takes_the_same_window_flags_as_film():
    args = cli.parse_args(["where", "dune", "--days", "7", "--from", "2026-09-09"])
    assert args.command == "where" and args.days == 7 and args.start == "2026-09-09"


def test_cinemas_and_favorites_together_is_an_error(client):
    import asyncio

    from pathe.cli import _dispatch
    from pathe.errors import PatheError

    args = cli.parse_args(["-c", "helmond", "-f", "where", "dune"])
    with pytest.raises(PatheError, match="niet allebei"):
        asyncio.run(_dispatch(args, client))


# ------------------------------------------------------------------ time flags

@pytest.mark.parametrize("value, minutes", [
    ("19:00", 19 * 60), ("9:30", 9 * 60 + 30), ("19", 19 * 60), ("0:00", 0), ("24:00", 24 * 60),
])
def test_parse_time(value, minutes):
    assert cli._parse_time(value) == dt.timedelta(minutes=minutes)


@pytest.mark.parametrize("value", ["25:00", "24:01", "19:60", "19:5", "7pm", "", "19.00"])
def test_parse_time_rejects_with_a_dutch_message(value):
    import argparse

    with pytest.raises(argparse.ArgumentTypeError) as exc:
        cli._parse_time(value)
    assert str(exc.value).startswith(f"onbegrijpelijke tijd: {value!r}")


def test_bad_time_is_a_usage_error(fake, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["programme", "--starts-after", "25:00"])
    assert exc.value.code == 2
    assert "onbegrijpelijke tijd" in capsys.readouterr().err


SCREENING_COMMANDS = [
    ["programme"], ["film", "dune"], ["tagged", "classics"], ["arthouse"], ["pride"],
    ["classics"], ["new"],
]


@pytest.mark.parametrize("command", SCREENING_COMMANDS)
def test_screening_flags_on_every_screening_command(command):
    args = cli.parse_args([*command, "--links", "--starts-after", "18", "--ends-before", "23:30"])
    assert args.links is True
    assert args.starts_after == dt.timedelta(hours=18)
    assert args.ends_before == dt.timedelta(hours=23, minutes=30)
    plain = cli.parse_args(command)
    assert plain.links is False and plain.starts_after is None and plain.ends_before is None


@pytest.mark.parametrize("command", [
    ["where", "dune"], ["upcoming"], ["search", "dune"], ["cinemas"], ["info", "dune"],
    ["cinema", "helmond"],
])
def test_screening_flags_are_rejected_where_there_are_no_screenings(command):
    with pytest.raises(SystemExit):
        cli.parse_args([*command, "--links"])


def test_new_defaults_to_a_week():
    assert cli.parse_args(["new"]).days == 7


def test_programme_links_and_window_end_to_end(fake, capsys):
    code, out = run(["programme", SUNDAY, "-c", "helmond", "--links", "--starts-after", "19:00",
                     "--ends-before", "23:00"], capsys)
    assert code == 0
    assert "https://s.pathe.nl/" in out and "10:30–" not in out and "21:15–23:21" not in out
    assert "buiten het tijdvenster" in out


# ------------------------------------------------------------------------ json

def test_json_flag_parses_on_either_side():
    assert cli.parse_args(["--json", "programme"]).json is True
    assert cli.parse_args(["programme", "--json"]).json is True
    assert cli.parse_args(["programme"]).json is False


def test_json_flag_before_the_subcommand_survives(fake, capsys):
    import json

    _, before = run(["--json", "programme", SUNDAY, "-c", "helmond"], capsys)
    _, after = run(["programme", SUNDAY, "-c", "helmond", "--json"], capsys)
    assert before == after
    assert json.loads(before)["date"] == SUNDAY


@pytest.mark.parametrize("argv", [
    ["cinemas"], ["cinema", "helmond"], ["programme", SUNDAY], ["film", "fuori", "--from", SUNDAY],
    ["where", "leviticus"], ["tagged", "classics", "--from", SUNDAY], ["arthouse", "--from", SUNDAY],
    ["pride", "--from", SUNDAY], ["classics", "--from", SUNDAY], ["new", "--from", SUNDAY],
    ["upcoming"], ["search", "dune"], ["info", "spider-man"],
])
def test_every_command_speaks_json(argv, fake, capsys):
    import json

    code, out = run(["--json", "-c", "helmond", *argv], capsys)
    assert code == 0
    assert isinstance(json.loads(out), dict)
    assert out.endswith("}\n")


def test_errors_stay_on_stderr_in_json_mode(fake, capsys):
    assert cli.main(["--json", "programme", "-c", "atlantis"]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "onbekende bioscoop" in captured.err


# ---------------------------------------------------------------- info, cinema

def test_info_command(fake, capsys):
    code, out = run(["info", "spider-man"], capsys)
    assert code == 0 and out.startswith("# Spider-Man: Brand New Day")
    assert "cinemas" not in fake[0].calls, "info never resolves cinemas"


@pytest.mark.parametrize("slug", ["helmond", "pathe-helmond"])
def test_cinema_command_resolves_like_dash_c(slug, fake, capsys):
    code, out = run(["cinema", slug], capsys)
    assert code == 0 and out.startswith("# Pathé Helmond\n")


def test_cinema_command_unknown_slug(fake, capsys):
    assert cli.main(["cinema", "atlantis"]) == 2
    assert "onbekende bioscoop: atlantis" in capsys.readouterr().err
