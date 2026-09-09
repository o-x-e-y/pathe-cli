"""Cinema slug resolution and defaults."""

from conftest import load

from pathe import config

KNOWN = [c["slug"] for c in load("cinemas.json")]


def test_default_set_is_the_four_in_reach(monkeypatch):
    monkeypatch.delenv("PATHE_CINEMAS", raising=False)
    assert config.default_cinemas() == [
        "pathe-helmond",
        "pathe-eindhoven",
        "pathe-tilburg-centrum",
        "pathe-tilburg-stappegoor",
    ]


def test_env_overrides_the_default(monkeypatch):
    monkeypatch.setenv("PATHE_CINEMAS", "pathe-breda, pathe-delft")
    assert config.default_cinemas() == ["pathe-breda", "pathe-delft"]


def test_blank_env_falls_back(monkeypatch):
    monkeypatch.setenv("PATHE_CINEMAS", "   ")
    assert config.default_cinemas() == config.DEFAULT_CINEMAS


def test_exact_slug_resolves():
    got, unknown = config.resolve(["pathe-helmond"], KNOWN)
    assert got == ["pathe-helmond"] and unknown == []


def test_short_name_gains_the_prefix():
    got, _ = config.resolve(["helmond", "eindhoven"], KNOWN)
    assert got == ["pathe-helmond", "pathe-eindhoven"]


def test_case_and_spaces_tolerated():
    got, _ = config.resolve(["  Helmond ", "Tilburg Centrum"], KNOWN)
    assert got == ["pathe-helmond", "pathe-tilburg-centrum"]


def test_unprefixed_cinema_still_resolves():
    """Tuschinski has no `pathe-` prefix, which is why resolution runs against
    the real slug list instead of doing string surgery."""
    got, unknown = config.resolve(["tuschinski"], KNOWN)
    assert got == ["koninklijk-theater-tuschinski"] and unknown == []


def test_ambiguous_substring_is_reported_not_guessed():
    got, unknown = config.resolve(["tilburg"], KNOWN)
    assert got == [] and unknown == ["tilburg"]


def test_unknown_is_reported():
    got, unknown = config.resolve(["atlantis"], KNOWN)
    assert got == [] and unknown == ["atlantis"]


def test_duplicates_collapse():
    got, _ = config.resolve(["helmond", "pathe-helmond"], KNOWN)
    assert got == ["pathe-helmond"]


def test_blank_entries_ignored():
    got, unknown = config.resolve(["helmond", "", "  "], KNOWN)
    assert got == ["pathe-helmond"] and unknown == []


def test_error_type_is_shared_between_api_and_errors():
    """`config` raises PatheError without importing the HTTP client, so the
    type has to live somewhere both modules can reach."""
    from pathe import api, errors

    assert api.PatheError is errors.PatheError


def test_suite_does_not_read_the_real_home_config():
    """The autouse fixture in conftest points XDG_CONFIG_HOME at a tmp dir, so
    a settings.json on the developer's machine cannot change test outcomes."""
    import os
    from pathlib import Path

    assert Path(os.environ["XDG_CONFIG_HOME"]) != Path.home() / ".config"
