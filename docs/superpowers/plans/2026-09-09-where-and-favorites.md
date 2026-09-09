# `where` and favourites — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `pathe where <titel>` — which cinemas play a film, in one request — and make the "my cinemas" set configurable from a settings file that a home-manager module writes.

**Architecture:** `GET /api/show/{slug}/cinemas` is the inverse of the cinema matrix already in use: it returns only the cinemas that have the title, each with the same `{days: {date: {tags, versions}}}` cell shape. One request replaces a 31-cinema fanout. Favourites move from a hard-coded list in `config.py` to `~/.config/pathe/settings.json`, with the built-in four kept as the no-config fallback. The flake exports a home-manager module that owns the options; the consuming config only sets values.

**Tech Stack:** Python 3.13, httpx, pytest + pytest-asyncio (all tests offline against recorded fixtures), Nix flake + home-manager.

**Spec:** `docs/superpowers/specs/2026-09-09-where-and-favorites-design.md`

**Before starting:** `cd ~/Repos/pathe-cli && nix develop` — every `pytest` below assumes that shell.

---

### Task 1: Move `PatheError` so `config` can raise it

`config.py` must raise `PatheError` for a malformed settings file, but importing
it from `api.py` would drag httpx into the config module. Give the exception its
own home and re-export it, so every existing `from .api import PatheError`
keeps working.

**Files:**
- Create: `src/pathe/errors.py`
- Modify: `src/pathe/api.py:31-32`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:

```python
def test_error_type_is_shared_between_api_and_errors():
    """`config` raises PatheError without importing the HTTP client, so the
    type has to live somewhere both modules can reach."""
    from pathe import api, errors

    assert api.PatheError is errors.PatheError
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py::test_error_type_is_shared_between_api_and_errors -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pathe.errors'`

- [ ] **Step 3: Create the module**

Create `src/pathe/errors.py`:

```python
"""The one exception type this package raises.

In its own module so `config` can raise it without importing `api`, which
would pull httpx in just to name an error.
"""


class PatheError(RuntimeError):
    pass
```

- [ ] **Step 4: Re-export from `api.py`**

In `src/pathe/api.py`, replace:

```python
class PatheError(RuntimeError):
    pass
```

with:

```python
from .errors import PatheError  # noqa: F401  (re-exported; imported as api.PatheError)
```

and move that line up with the other relative import, so the file reads:

```python
from .cache import CATALOGUE_TTL, SHOWTIMES_TTL, Cache
from .errors import PatheError  # noqa: F401  (re-exported; imported as api.PatheError)
```

- [ ] **Step 5: Run the whole suite**

Run: `pytest -q`
Expected: 140 passed (139 existing + 1 new)

- [ ] **Step 6: Commit**

```bash
git add src/pathe/errors.py src/pathe/api.py tests/test_config.py
git commit -m "refactor: give PatheError its own module

config needs to raise it without importing the HTTP client."
```

---

### Task 2: Isolate tests from the developer's real config

Every later task reads `$XDG_CONFIG_HOME/pathe/settings.json`. Without this,
the suite passes or fails depending on whose machine it runs on.

**Files:**
- Modify: `tests/conftest.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:

```python
def test_suite_does_not_read_the_real_home_config():
    """The autouse fixture in conftest points XDG_CONFIG_HOME at a tmp dir, so
    a settings.json on the developer's machine cannot change test outcomes."""
    import os
    from pathlib import Path

    assert Path(os.environ["XDG_CONFIG_HOME"]) != Path.home() / ".config"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py::test_suite_does_not_read_the_real_home_config -v`
Expected: FAIL with `KeyError: 'XDG_CONFIG_HOME'` (or a pass-by-accident if the
developer happens to export it — the fixture in step 3 makes it deterministic
either way)

- [ ] **Step 3: Add the autouse fixture**

Append to `tests/conftest.py`:

```python
@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """No test may read the machine's real ~/.config/pathe/settings.json, and
    no test may inherit a PATHE_CINEMAS from the shell that ran pytest."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("PATHE_CINEMAS", raising=False)
```

- [ ] **Step 4: Run the whole suite**

Run: `pytest -q`
Expected: 141 passed

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_config.py
git commit -m "test: isolate the suite from the machine's pathe config"
```

---

### Task 3: Read favourites from `settings.json`

**Files:**
- Modify: `src/pathe/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
import json


def write_settings(payload):
    """Write a settings.json into the tmp XDG_CONFIG_HOME the autouse fixture
    set up, and return its path."""
    import os
    from pathlib import Path

    path = Path(os.environ["XDG_CONFIG_HOME"]) / "pathe" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload))
    return path


def test_settings_path_follows_xdg():
    import os
    from pathlib import Path

    assert config.settings_path() == (
        Path(os.environ["XDG_CONFIG_HOME"]) / "pathe" / "settings.json"
    )


def test_missing_settings_file_is_not_an_error():
    assert config.load_settings() == {}


def test_favorites_default_to_the_built_in_four():
    assert config.favorites() == config.DEFAULT_CINEMAS


def test_favorites_come_from_the_file():
    write_settings({"favorites": ["pathe-breda", "pathe-delft"]})
    assert config.favorites() == ["pathe-breda", "pathe-delft"]


def test_unknown_keys_in_the_file_are_ignored():
    write_settings({"favorites": ["pathe-breda"], "kleur": "paars"})
    assert config.favorites() == ["pathe-breda"]


def test_empty_favorites_list_falls_back():
    write_settings({"favorites": []})
    assert config.favorites() == config.DEFAULT_CINEMAS


def test_malformed_json_is_fatal():
    """The file is machine-generated by Nix; a broken one is a bug to surface,
    not something to quietly fall back from."""
    from pathe.errors import PatheError

    path = write_settings("{ dit is geen json")
    with pytest.raises(PatheError, match=str(path)):
        config.load_settings()


def test_non_object_json_is_fatal():
    from pathe.errors import PatheError

    write_settings("[1, 2, 3]")
    with pytest.raises(PatheError, match="JSON-object"):
        config.load_settings()


def test_favorites_of_the_wrong_type_is_fatal():
    from pathe.errors import PatheError

    write_settings({"favorites": "pathe-breda"})
    with pytest.raises(PatheError, match="lijst strings"):
        config.favorites()


def test_env_wins_over_the_file(monkeypatch):
    """settings.json is declarative and permanent; PATHE_CINEMAS is the ad-hoc
    override for one shell, so it is the more specific signal."""
    write_settings({"favorites": ["pathe-breda"]})
    monkeypatch.setenv("PATHE_CINEMAS", "pathe-delft")
    assert config.default_cinemas() == ["pathe-delft"]


def test_favorites_ignore_the_env(monkeypatch):
    """`-f` means *my* cinemas, whatever this shell says."""
    write_settings({"favorites": ["pathe-breda"]})
    monkeypatch.setenv("PATHE_CINEMAS", "pathe-delft")
    assert config.favorites() == ["pathe-breda"]


def test_default_falls_through_the_file_when_env_is_unset():
    write_settings({"favorites": ["pathe-breda"]})
    assert config.default_cinemas() == ["pathe-breda"]
```

Also add `import pytest` to the top of `tests/test_config.py` (it currently has
no pytest import).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -q`
Expected: FAIL with `AttributeError: module 'pathe.config' has no attribute 'settings_path'`

- [ ] **Step 3: Implement**

In `src/pathe/config.py`, replace the module docstring and imports:

```python
"""Defaults, overridable from a settings file and from the environment.

Precedence, most specific first:

    -c <slugs>  >  PATHE_CINEMAS  >  settings.json favorites  >  DEFAULT_CINEMAS

The env var beats the file because the file is declarative and permanent --
written by a home-manager module -- while PATHE_CINEMAS is the ad-hoc override
for a single shell.
"""

import json
import os
from pathlib import Path

from .errors import PatheError
```

Keep `DEFAULT_CINEMAS` and `DEFAULT_HORIZON_DAYS` as they are, then replace
`default_cinemas()` with:

```python
def settings_path():
    root = os.environ.get("XDG_CONFIG_HOME", "").strip()
    base = Path(root) if root else Path.home() / ".config"
    return base / "pathe" / "settings.json"


def load_settings():
    """The parsed settings file, or `{}` when there is none.

    A file that exists but does not parse raises: it is generated by Nix, so a
    broken one means the config is wrong and should say so rather than
    silently reverting to the built-in defaults.
    """
    path = settings_path()
    try:
        raw = path.read_text()
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise PatheError(f"{path}: {exc}") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PatheError(f"{path}: geen geldige JSON ({exc})") from exc
    if not isinstance(parsed, dict):
        raise PatheError(f"{path}: verwacht een JSON-object")
    return parsed


def favorites():
    """The configured cinemas, or the built-in four.

    Deliberately ignores PATHE_CINEMAS: `-f` means *my* cinemas, whatever the
    current shell has been told.
    """
    configured = load_settings().get("favorites")
    if configured is None:
        return list(DEFAULT_CINEMAS)
    if not isinstance(configured, list) or not all(isinstance(s, str) for s in configured):
        raise PatheError(f"{settings_path()}: `favorites` moet een lijst strings zijn")
    kept = [s.strip() for s in configured if s.strip()]
    return kept or list(DEFAULT_CINEMAS)


def default_cinemas():
    raw = os.environ.get("PATHE_CINEMAS", "").strip()
    if not raw:
        return favorites()
    return [s.strip() for s in raw.split(",") if s.strip()]
```

Leave `resolve()` untouched — entries from the file go through it exactly as
`-c` values do, so `"stappegoor"` in the file resolves and a typo still
produces the existing `onbekende bioscoop` error.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -q`
Expected: all pass

- [ ] **Step 5: Run the whole suite**

Run: `pytest -q`
Expected: all pass (12 new tests in test_config.py)

- [ ] **Step 6: Commit**

```bash
git add src/pathe/config.py tests/test_config.py
git commit -m "feat: read favourite cinemas from ~/.config/pathe/settings.json

Env var still wins; the built-in four remain the no-config fallback."
```

---

### Task 4: Record the `/show/{slug}/cinemas` fixture and add the client method

**Files:**
- Create: `tests/fixtures/show-cinemas/leviticus-53403.json`
- Modify: `src/pathe/api.py`, `tests/conftest.py`
- Test: `tests/test_queries.py`

- [ ] **Step 1: Record the fixture**

```bash
mkdir -p tests/fixtures/show-cinemas
curl -s "https://www.pathe.nl/api/show/leviticus-53403/cinemas" \
  -H 'Accept: application/json' \
  -H 'Accept-Language: nl-NL,nl;q=0.9' \
  -H 'User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36' \
  | python -m json.tool > tests/fixtures/show-cinemas/leviticus-53403.json
```

Verify it has the nine cinemas the design recorded:

```bash
python -c "import json;d=json.load(open('tests/fixtures/show-cinemas/leviticus-53403.json'));print(len(d), sorted(d))"
```

Expected: `9 ['pathe-amsterdam-noord', 'pathe-arena', 'pathe-arnhem', 'pathe-de-kuip', 'pathe-de-munt', 'pathe-schiedam', 'pathe-spuimarkt', 'pathe-tilburg-stappegoor', 'pathe-zwolle']`

If the live programme has moved on since 2026-09-09 and the shape or the set
differs, keep whatever comes back and adjust the expected values in Tasks 6-7
to match the recording — the fixture is the source of truth, not this plan.

- [ ] **Step 2: Add `show_cinemas` to the fake client**

In `tests/conftest.py`, add to `FakeClient` after `cinema_matrix`:

```python
    async def show_cinemas(self, slug):
        self.calls.append(f"show_cinemas:{slug}")
        try:
            return load(f"show-cinemas/{slug}.json")
        except FileNotFoundError:
            return {}
```

- [ ] **Step 3: Write the failing test**

Append to `tests/test_queries.py`:

```python
@pytest.mark.anyio
async def test_show_cinemas_is_one_request(client):
    """The whole point of the endpoint: the field is one call, not 31."""
    from pathe.api import PatheClient

    assert hasattr(PatheClient, "show_cinemas")
    payload = await client.show_cinemas("leviticus-53403")
    assert set(payload) and client.calls == ["show_cinemas:leviticus-53403"]
```

Check the top of `tests/test_queries.py` for how existing async tests are
marked and copy that marker rather than the one written above if it differs.

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_queries.py::test_show_cinemas_is_one_request -v`
Expected: FAIL on the `hasattr` assertion

- [ ] **Step 5: Implement**

In `src/pathe/api.py`, add after `cinema_matrix`:

```python
    async def show_cinemas(self, slug):
        """Which cinemas play `slug`, and on which dates.

        The inverse of `cinema_matrix`: same cell shape -- tags, versions, the
        lot -- but keyed by cinema instead of by title, and containing only the
        cinemas that actually have it. One request answers "where does this
        play", where asking each cinema in turn costs thirty-one.

        An unknown slug returns `{}` with a 200, not a 404.
        """
        return await self._get(f"/show/{slug}/cinemas", CATALOGUE_TTL)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_queries.py::test_show_cinemas_is_one_request -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add tests/fixtures/show-cinemas src/pathe/api.py tests/conftest.py tests/test_queries.py
git commit -m "feat: wrap /show/{slug}/cinemas

The inverse of the cinema matrix, and the one request that answers
'where does this play'."
```

---

### Task 5: `playing_dates` in the catalogue

**Files:**
- Modify: `src/pathe/catalogue.py`
- Test: `tests/test_catalogue.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_catalogue.py`:

```python
def test_playing_dates_keeps_only_dates_in_the_window():
    from pathe.catalogue import playing_dates

    payload = {
        "pathe-arnhem": {"days": {"2026-09-09": {}, "2026-09-10": {}, "2026-09-20": {}}},
    }
    assert playing_dates(payload, ["2026-09-09", "2026-09-10"]) == {
        "pathe-arnhem": ["2026-09-09", "2026-09-10"]
    }


def test_playing_dates_drops_cinemas_with_nothing_in_the_window():
    from pathe.catalogue import playing_dates

    payload = {"pathe-arnhem": {"days": {"2026-09-20": {}}}}
    assert playing_dates(payload, ["2026-09-09"]) == {}


def test_playing_dates_sorts_and_survives_an_empty_payload():
    from pathe.catalogue import playing_dates

    payload = {"pathe-arnhem": {"days": {"2026-09-10": {}, "2026-09-09": {}}}}
    assert playing_dates(payload, ["2026-09-09", "2026-09-10"])["pathe-arnhem"] == [
        "2026-09-09",
        "2026-09-10",
    ]
    assert playing_dates({}, ["2026-09-09"]) == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_catalogue.py -q -k playing_dates`
Expected: FAIL with `ImportError: cannot import name 'playing_dates'`

- [ ] **Step 3: Implement**

In `src/pathe/catalogue.py`, add after `cells()`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_catalogue.py -q -k playing_dates`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/pathe/catalogue.py tests/test_catalogue.py
git commit -m "feat: playing_dates over the show-cinemas payload"
```

---

### Task 6: Render the cinema rows

**Files:**
- Modify: `src/pathe/render.py`
- Test: `tests/test_render.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_render.py`:

```python
def test_short_date():
    from pathe import render

    assert render.short_date("2026-09-16") == "wo 16 sep"
    assert render.short_date("2026-03-01") == "zo 1 mrt"
    assert render.short_date("nonsense") == "nonsense"


def test_date_span_of_a_single_day():
    from pathe import render

    assert render.date_span(["2026-09-09"]) == "wo 9 sep"


def test_date_span_of_a_full_run():
    from pathe import render

    days = [f"2026-09-{d:02d}" for d in range(9, 17)]
    assert render.date_span(days) == "wo 9 sep – wo 16 sep"


def test_date_span_counts_days_when_the_run_has_gaps():
    """A bare span would claim Zwolle plays it every day between the ends; it
    plays five of those seven."""
    from pathe import render

    days = ["2026-09-09", "2026-09-10", "2026-09-12", "2026-09-14", "2026-09-15"]
    assert render.date_span(days) == "wo 9 sep – di 15 sep (5 dagen)"


def test_cinema_rows_align_the_spans():
    from pathe import render

    rows = render.cinema_rows([
        ("pathe-arena", "Pathé Arena", ["2026-09-09"]),
        ("pathe-zwolle", "Pathé Zwolle Lang", ["2026-09-09"]),
    ])
    assert rows[0] == "  `pathe-arena`\n     Pathé Arena        wo 9 sep"
    assert rows[1] == "  `pathe-zwolle`\n     Pathé Zwolle Lang  wo 9 sep"


def test_cinema_rows_of_nothing():
    from pathe import render

    assert render.cinema_rows([]) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_render.py -q -k "short_date or date_span or cinema_rows"`
Expected: FAIL with `AttributeError: module 'pathe.render' has no attribute 'short_date'`

- [ ] **Step 3: Implement**

In `src/pathe/render.py`, add `SHORT_MONTHS` under `MONTHS`:

```python
SHORT_MONTHS = [
    "jan", "feb", "mrt", "apr", "mei", "jun",
    "jul", "aug", "sep", "okt", "nov", "dec",
]
```

and add after `dutch_date`:

```python
def short_date(iso):
    """`2026-09-16` -> `wo 16 sep`. The long form is for a heading over one
    day's screenings; a list of cinemas needs something that stays in a column.
    """
    try:
        day = dt.date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso
    return f"{DAYS[day.weekday()][:2]} {day.day} {SHORT_MONTHS[day.month - 1]}"


def date_span(days):
    """The run of a film at one cinema.

    Prints the day count when the run has holes in it: a bare `wo 9 – di 15`
    would claim eight days of screenings where there are five, and the gap is
    exactly the thing you would plan around.
    """
    if not days:
        return ""
    first, last = days[0], days[-1]
    if first == last:
        return short_date(first)
    out = f"{short_date(first)} – {short_date(last)}"
    try:
        width = (dt.date.fromisoformat(last) - dt.date.fromisoformat(first)).days + 1
    except (TypeError, ValueError):
        return out
    if len(days) < width:
        out += f" ({len(days)} dagen)"
    return out


def cinema_rows(entries):
    """`[(slug, name, days), ...]` -> one block per cinema.

    The slug gets its own line because it is what you paste into `-c`; the
    names are padded so the spans line up down the block.
    """
    width = max((len(name) for _, name, _ in entries), default=0)
    return [
        f"  `{slug}`\n     {name.ljust(width)}  {date_span(days)}"
        for slug, name, days in entries
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_render.py -q -k "short_date or date_span or cinema_rows"`
Expected: 6 passed

- [ ] **Step 5: Run the whole suite**

Run: `pytest -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/pathe/render.py tests/test_render.py
git commit -m "feat: render a cinema list with date spans"
```

---

### Task 7: The `where` query

**Files:**
- Modify: `src/pathe/queries.py`
- Test: `tests/test_queries.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_queries.py` (copy the async marker used by the other
tests in this file):

```python
FOUR = [
    "pathe-helmond",
    "pathe-eindhoven",
    "pathe-tilburg-centrum",
    "pathe-tilburg-stappegoor",
]
WEEK = [f"2026-09-{d:02d}" for d in range(9, 17)]


@pytest.mark.anyio
async def test_where_splits_mine_from_the_rest(client):
    from pathe import queries

    out = await queries.where(client, "leviticus", FOUR, WEEK)
    assert out.startswith("# Leviticus — 9 van 31 bioscopen")
    assert "## Jouw bioscopen" in out
    assert "`pathe-tilburg-stappegoor`" in out.split("## Elders")[0]
    assert "`pathe-arena`" in out.split("## Elders")[1]


@pytest.mark.anyio
async def test_where_names_the_favourites_that_do_not_have_it(client):
    """An empty first section would be ambiguous -- no cinemas, or no
    favourites configured?"""
    from pathe import queries

    out = await queries.where(client, "leviticus", FOUR, WEEK)
    mine = out.split("## Elders")[0]
    assert "niet in: helmond, eindhoven, tilburg-centrum" in mine


@pytest.mark.anyio
async def test_where_counts_the_others(client):
    from pathe import queries

    out = await queries.where(client, "leviticus", FOUR, WEEK)
    assert "## Elders (8)" in out


@pytest.mark.anyio
async def test_where_only_favourites_drops_the_rest(client):
    from pathe import queries

    out = await queries.where(client, "leviticus", FOUR, WEEK, only_favorites=True)
    assert "## Jouw bioscopen" in out and "## Elders" not in out


@pytest.mark.anyio
async def test_where_narrows_to_the_window(client):
    from pathe import queries

    out = await queries.where(client, "leviticus", FOUR, ["2026-09-09"])
    assert "wo 9 sep" in out and "wo 16 sep" not in out


@pytest.mark.anyio
async def test_where_fetches_no_showtimes(client):
    """`where` answers where, not when. Pulling showtimes would put the
    31-cinema cost straight back in."""
    from pathe import queries

    await queries.where(client, "leviticus", FOUR, WEEK)
    assert client.showtime_calls == []


@pytest.mark.anyio
async def test_where_on_an_unknown_title(client):
    from pathe import queries

    out = await queries.where(client, "zzzznietbestaand", FOUR, WEEK)
    assert "Zoeken: “zzzznietbestaand”" in out


@pytest.mark.anyio
async def test_where_when_the_title_plays_nowhere(client):
    """Known title, no cinemas in the window -- say so, rather than printing
    two empty sections."""
    from pathe import queries

    out = await queries.where(client, "leviticus", FOUR, ["2027-01-01"])
    assert "draait nergens in dit venster" in out
    assert "## Elders" not in out


@pytest.mark.anyio
async def test_where_notes_other_title_matches(client):
    """Same affordance `film` has: the catalogue title often differs from the
    spoken one, so name the near misses."""
    from pathe import queries

    out = await queries.where(client, "the", FOUR, WEEK)
    assert "ook gevonden:" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_queries.py -q -k where`
Expected: FAIL with `AttributeError: module 'pathe.queries' has no attribute 'where'`

- [ ] **Step 3: Implement**

In `src/pathe/queries.py`, change the import line:

```python
from .catalogue import Catalogue, cells, parse_screenings, playing_dates
```

add next to `_cinema_names`:

```python
def _cinema_cities(cinemas_payload):
    return {c["slug"]: c.get("citySlug") or "" for c in cinemas_payload}


def _short(slug):
    """`pathe-helmond` -> `helmond`. For prose, where the prefix is noise."""
    return slug[len("pathe-"):] if slug.startswith("pathe-") else slug
```

and add after `film_showtimes`:

```python
async def where(client, query, mine, dates, *, only_favorites=False):
    """Which cinemas play one title -- the field, not the times.

    Costs one `show_cinemas` request plus the two catalogue ones, because the
    endpoint is the cinema matrix seen from the film's side and already lists
    only the cinemas that have it. Asking the same question through
    `film_showtimes` means a matrix request per cinema and a showtimes fanout
    on top, for an answer you were going to narrow anyway.

    Deliberately fetches no showtimes: `where` is the step before `film`.
    """
    catalogue = await _catalogue(client)
    hits = catalogue.search(query)
    if not hits:
        return render.document([render.section(f"Zoeken: “{query}”", [])])
    film = hits[0]

    playing = playing_dates(await client.show_cinemas(film.slug), dates)
    cinemas_payload = await client.cinemas()
    names = _cinema_names(cinemas_payload)
    cities = _cinema_cities(cinemas_payload)

    header = (
        f"# {film.title} — {len(playing)} van {len(cinemas_payload)} bioscopen\n"
        f"{render.film_line(film)}"
    )
    note = ""
    other = hits[1:4]
    if other:
        note = "ook gevonden: " + ", ".join(f"{f.title} (`{f.slug}`)" for f in other)

    if not playing:
        body = "_draait nergens in dit venster._"
        if note:
            body += f"\n\n_{note}_"
        return f"{header}\n\n{body}\n"

    kept = [c for c in mine if c in playing]
    missing = [c for c in mine if c not in playing]
    rest = sorted(
        (c for c in playing if c not in mine),
        key=lambda c: (cities.get(c, ""), names.get(c, c)),
    )

    blocks = render.cinema_rows([(c, names.get(c, c), playing[c]) for c in kept])
    if missing:
        blocks.append("niet in: " + ", ".join(_short(c) for c in missing))
    sections = [render.section("Jouw bioscopen", blocks)]
    if not only_favorites:
        sections.append(
            render.section(
                f"Elders ({len(rest)})",
                render.cinema_rows([(c, names.get(c, c), playing[c]) for c in rest]),
            )
        )
    return header + "\n\n" + render.document(sections, note=note)
```

Update the module docstring's first line, which still says "The five
operations", to "The seven operations".

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_queries.py -q -k where`
Expected: 9 passed

- [ ] **Step 5: Run the whole suite**

Run: `pytest -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/pathe/queries.py tests/test_queries.py
git commit -m "feat: where() -- which cinemas play a title, in one request"
```

---

### Task 8: Wire `where` and `-f` into the CLI

**Files:**
- Modify: `src/pathe/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py` (match the existing file's import style):

```python
def test_favorites_flag_parses_on_either_side():
    """The SUPPRESS trap CLAUDE.md documents: a flag given before the
    subcommand must survive the subparser's own parse."""
    from pathe.cli import parse_args

    assert parse_args(["-f", "where", "dune"]).favorites is True
    assert parse_args(["where", "dune", "-f"]).favorites is True
    assert parse_args(["where", "dune"]).favorites is False


def test_where_takes_the_same_window_flags_as_film():
    from pathe.cli import parse_args

    args = parse_args(["where", "dune", "--days", "7", "--from", "2026-09-09"])
    assert args.command == "where" and args.days == 7 and args.start == "2026-09-09"


def test_cinemas_and_favorites_together_is_an_error(client):
    import asyncio

    from pathe.cli import _dispatch, parse_args
    from pathe.errors import PatheError

    args = parse_args(["-c", "helmond", "-f", "where", "dune"])
    with pytest.raises(PatheError, match="niet allebei"):
        asyncio.run(_dispatch(args, client))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py -q -k "favorites or where"`
Expected: FAIL with `AttributeError: 'Namespace' object has no attribute 'favorites'`

- [ ] **Step 3: Implement**

In `src/pathe/cli.py`:

Add to `GLOBAL_DEFAULTS`, after `"cinemas": None,`:

```python
    "favorites": False,
```

Add to `_global_flags()`, after the `--cinemas` argument:

```python
    p.add_argument("--favorites", "-f", action="store_true", default=argparse.SUPPRESS,
                   help="gebruik je favorieten uit settings.json")
```

Change the config import to pull the new function under a non-colliding name:

```python
from .config import (
    DEFAULT_HORIZON_DAYS,
    default_cinemas,
    favorites as configured_favorites,
    resolve,
)
```

Register the subcommand, directly after the `film` block in `build_parser()`:

```python
    p = add("where", "in welke bioscopen een film draait")
    p.add_argument("query", help="titel (of deel daarvan)")
    p.add_argument("--days", type=int, default=DEFAULT_HORIZON_DAYS)
    p.add_argument("--from", dest="start", default="today")
```

In `_dispatch`, replace the `requested = ...` line with:

```python
    if args.cinemas and args.favorites:
        raise PatheError("kies `-c` of `-f`, niet allebei")
    if args.favorites:
        requested = configured_favorites()
    elif args.cinemas:
        requested = args.cinemas.split(",")
    else:
        requested = default_cinemas()
```

and add the dispatch branch after the `film` one:

```python
    if command == "where":
        dates = date_range(args.days, dt.date.fromisoformat(_parse_date(args.start)))
        return await queries.where(client, args.query, cinemas, dates,
                                   only_favorites=args.favorites)
```

`where` reuses the resolved `cinemas` as its "Jouw bioscopen" list, so
`-c breda,nijmegen` asks the same question about a different pair without any
special-casing.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli.py -q -k "favorites or where"`
Expected: 3 passed

- [ ] **Step 5: Run the whole suite**

Run: `pytest -q`
Expected: all pass

- [ ] **Step 6: Check it against the live API**

```bash
PYTHONPATH=src python -m pathe where leviticus --days 7
PYTHONPATH=src python -m pathe where leviticus --days 7 -f
```

Expected: the first prints `# Leviticus — 9 van 31 bioscopen` with Stappegoor
under `## Jouw bioscopen`, a `niet in:` line, and `## Elders (8)`; the second
prints the same first section and no `Elders`.

- [ ] **Step 7: Commit**

```bash
git add src/pathe/cli.py tests/test_cli.py
git commit -m "feat: pathe where, and -f for the configured favourites"
```

---

### Task 9: Documentation

`--help` is the reference for both a person and an agent, so it is not
optional polish.

**Files:**
- Modify: `src/pathe/cli.py` (the `EPILOG`), `README.md`, `CLAUDE.md`

- [ ] **Step 1: Update the epilog**

In `src/pathe/cli.py`, replace the `bioscopen` block of `EPILOG` with:

```
bioscopen (default: je favorieten, anders helmond, eindhoven, tilburg-centrum,
           tilburg-stappegoor)
  -c neemt slugs met of zonder `pathe-` prefix, komma-gescheiden.
  -f gebruikt je favorieten uit ~/.config/pathe/settings.json, ook als
     PATHE_CINEMAS gezet is. -c en -f samen is een fout.
  `pathe cinemas` toont alle 31 met de formaten die ze hebben.
  Volgorde: -c  >  PATHE_CINEMAS  >  settings.json  >  ingebouwde vier.

  settings.json ziet er zo uit:
    { "favorites": ["helmond", "tilburg-stappegoor"] }
```

and add to the `voorbeelden` block, after the `film` line:

```
  pathe where leviticus                  in welke bioscopen draait het
  pathe where leviticus -f               alleen die van jou
```

- [ ] **Step 2: Verify the help renders**

Run: `PYTHONPATH=src python -m pathe --help`
Expected: the new `where` row in the command list and both new epilog blocks,
with no argparse formatting damage

- [ ] **Step 3: Update `README.md`**

In the `## What it does` table, add a row directly under the `pathe film` one:

```markdown
| `pathe where <titel>` | which cinemas play it at all — one request |
```

and change the `pathe film` row to `when and at what times one film plays`.
Then add to `## Notes`:

```markdown
Favourite cinemas come from `~/.config/pathe/settings.json`:

    { "favorites": ["helmond", "tilburg-stappegoor"] }

They are what `-c` overrides and what `-f` selects. Entries resolve the same
way `-c` values do, so the bare name works. Order of precedence: `-c`, then
`PATHE_CINEMAS`, then this file, then the built-in four.
```

- [ ] **Step 4: Update `CLAUDE.md`**

In the "Common calls" block add:

```sh
pathe where "leviticus"               # which cinemas have it -- one request
```

and after that block, add a line to the layout table's `config.py` row or just
below it:

```
Favourites live in `~/.config/pathe/settings.json` (`{"favorites": [...]}`),
written by the home-manager module the flake exports. `-f` selects them even
when `PATHE_CINEMAS` is set.
```

- [ ] **Step 5: Commit**

```bash
git add src/pathe/cli.py README.md CLAUDE.md
git commit -m "docs: where, favourites and the settings file"
```

---

### Task 10: The home-manager module

**Files:**
- Create: `nix/hm-module.nix`
- Modify: `flake.nix`

- [ ] **Step 1: Write the module**

Create `nix/hm-module.nix`:

```nix
{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.programs.pathe;
in
{
  options.programs.pathe = {
    enable = lib.mkEnableOption "the pathe CLI";

    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.pathe-cli;
      defaultText = lib.literalExpression "pkgs.pathe-cli";
      description = ''
        The package to install. The default needs this flake's
        `overlays.default` in `nixpkgs.overlays`.
      '';
    };

    favorites = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      example = [
        "helmond"
        "tilburg-stappegoor"
      ];
      description = ''
        Cinemas used when no `-c` is given, and what `-f` selects.

        An entry may be a full slug (`pathe-helmond`), the slug without the
        prefix (`helmond`), or any unique substring of one; `pathe cinemas`
        lists them all. Note that not every cinema carries the prefix --
        `koninklijk-theater-tuschinski` does not.

        Left empty, no settings file is written and the CLI keeps its built-in
        default.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    home.packages = [ cfg.package ];

    xdg.configFile."pathe/settings.json" = lib.mkIf (cfg.favorites != [ ]) {
      text = builtins.toJSON { favorites = cfg.favorites; };
    };
  };
}
```

- [ ] **Step 2: Export it from the flake**

In `flake.nix`, in the trailing non-system attribute set, alongside
`overlays.default`:

```nix
    // {
      overlays.default = final: _prev: {
        pathe-cli = final.callPackage ./nix/package.nix { };
      };

      homeManagerModules.default = ./nix/hm-module.nix;
    };
```

- [ ] **Step 3: Verify the flake evaluates**

```bash
nix flake check 2>&1 | tail -20
nix eval .#homeManagerModules.default --apply builtins.typeOf
```

Expected: `nix flake check` clean, and the eval prints `"path"`.

- [ ] **Step 4: Commit**

```bash
git add nix/hm-module.nix flake.nix
git commit -m "feat: export a home-manager module

Options live with the code that reads them; consumers only set values."
```

---

### Task 11: Wire it into `~/nixos`

Everything below is in `/home/oxey/nixos`, a separate git repository — commit
there, not in `pathe-cli`.

**Files:**
- Create: `/home/oxey/nixos/home/programs/pathe/default.nix`
- Modify: `/home/oxey/nixos/flake.nix`, `/home/oxey/nixos/home/programs/default.nix`, `/home/oxey/nixos/home/programs/claude-code/pathe/default.nix`

- [ ] **Step 1: Point the flake input at the local checkout for now**

The input is `github:o-x-e-y/pathe-cli`, so until the CLI work is pushed the
module does not exist upstream. For the rebuild in step 6, override it:

```bash
cd /home/oxey/nixos
nix flake lock --override-input pathe-cli /home/oxey/Repos/pathe-cli
```

Undo this with `nix flake lock --override-input pathe-cli github:o-x-e-y/pathe-cli`
once `pathe-cli` is pushed, and update the lock.

- [ ] **Step 2: Load the module**

In `/home/oxey/nixos/flake.nix`, add to `home-manager.sharedModules`:

```nix
            home-manager.sharedModules = [
              plasma-manager.homeModules.plasma-manager
              zed-extensions.homeManagerModules.default
              deepseek-harness.homeModules.default
              pathe-cli.homeManagerModules.default
            ];
```

- [ ] **Step 3: Add the local module**

Create `/home/oxey/nixos/home/programs/pathe/default.nix`:

```nix
{
  config,
  lib,
  ...
}:
let
  cfg = config.apps.pathe;
in
{
  options.apps.pathe = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Enable the pathe CLI";
    };
  };

  # The options come from the pathe-cli flake's home-manager module, loaded in
  # ../../../flake.nix; this only sets the values. The package lives here
  # rather than in claude-code/pathe because pathe is a tool that Claude also
  # uses, not the other way round -- hanging it off `apps.claude-code.enable`
  # would take it off the system whenever that is turned off.
  config = lib.mkIf cfg.enable {
    programs.pathe = {
      enable = true;
      favorites = [
        "pathe-helmond"
        "pathe-eindhoven"
        "pathe-tilburg-centrum"
        "pathe-tilburg-stappegoor"
      ];
    };
  };
}
```

- [ ] **Step 4: Import it**

In `/home/oxey/nixos/home/programs/default.nix`, add `./pathe` to the imports
list, in alphabetical position between `./osu-lazer` and `./plasma`.

- [ ] **Step 5: Take the package out of the claude-code module**

In `/home/oxey/nixos/home/programs/claude-code/pathe/default.nix`, delete:

```nix
    home.packages = [ pkgs.pathe-cli ];
```

Remove `pkgs,` from the function arguments — it has no other use in the file.
Then replace the comment above `description` that begins "pkgs.pathe-cli comes
from the pathe-cli flake input's overlay" with:

```nix
  # The package and the favourites config live in ../../pathe; this module owns
  # only the agent-facing surface. A CLI and not an MCP server, for the reason
```

keeping the rest of that comment intact.

- [ ] **Step 6: Rebuild**

```bash
cd /home/oxey/nixos
sudo nixos-rebuild switch --flake .#$(hostname)
```

Expected: builds; if the flake's `nixosConfigurations` attribute is not named
after the hostname, use the name in `flake.nix`.

- [ ] **Step 7: Verify the config landed**

```bash
cat ~/.config/pathe/settings.json
pathe where leviticus --days 7
```

Expected: the JSON holds the four slugs, and `where` puts Stappegoor under
`## Jouw bioscopen`.

- [ ] **Step 8: Commit**

```bash
cd /home/oxey/nixos
git add home/programs/pathe home/programs/default.nix home/programs/claude-code/pathe/default.nix flake.nix flake.lock
git commit -m "pathe: own module for the CLI and its favourites

The package hung off apps.claude-code.enable, which is the wrong
dependency -- pathe is a tool Claude also uses."
```

---

### Task 12: Update the slash command

**Files:**
- Modify: `/home/oxey/nixos/home/programs/claude-code/pathe/command.md`

- [ ] **Step 1: Add `where` to the command table**

In the "Choosing the command" table, add above the `film` row:

```markdown
| where a film is playing at all | `pathe where "<titel>"` |
```

and change the `film` row's description to `when and at what times a particular
film plays`.

- [ ] **Step 2: Add the two-step note**

Under "Details that matter", add:

```markdown
**Where versus when.** `where` costs one request and lists only the cinemas
that have the title; `film` fetches actual times for the cinemas you name. For
"where can I see X" run `where` first, then `film -c <the ones that matter>`.
Do not answer a "where" question by passing all 31 slugs to `film`.

**Favourites.** The default set comes from `~/.config/pathe/settings.json`.
`-f` selects it explicitly, which is what you want on `where` when the question
is only about the user's own cinemas.
```

- [ ] **Step 3: Rebuild and check the command file**

```bash
cd /home/oxey/nixos && sudo nixos-rebuild switch --flake .#$(hostname)
grep -A2 "where a film" ~/.claude/commands/pathe.md
```

Expected: the new row is in the generated command file.

- [ ] **Step 4: Commit**

```bash
cd /home/oxey/nixos
git add home/programs/claude-code/pathe/command.md
git commit -m "pathe command: teach it where, and the where-then-film order"
```

---

### Task 13: Final verification

- [ ] **Step 1: Full suite**

Run: `cd ~/Repos/pathe-cli && nix develop -c pytest -q`
Expected: all pass, no skips

- [ ] **Step 2: Lint**

Run: `nix develop -c ruff check src tests`
Expected: clean (the `# noqa: F401` in Task 1 is the only suppression)

- [ ] **Step 3: Package build**

Run: `nix build .# && ./result/bin/pathe where leviticus --days 7`
Expected: builds and prints the split output

- [ ] **Step 4: Confirm the precedence chain end to end**

```bash
PATHE_CINEMAS=pathe-breda ./result/bin/pathe where leviticus --days 7 | head -8
PATHE_CINEMAS=pathe-breda ./result/bin/pathe where leviticus --days 7 -f | head -8
```

Expected: the first treats Breda as "yours" (and lists it under `niet in:`,
since Breda does not have Leviticus); the second ignores the env var and shows
the four from `settings.json`.
