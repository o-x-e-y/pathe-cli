# Booking links, time filters, `new`, `info`, `cinema` and `--json`

Date: 2026-11-20. Scope agreed with the user. Nothing here needs auth: every
endpoint is an unauthenticated GET and the tool still cannot book anything -- it
only *prints* the booking URL Pathé already hands out.

## Ground rules (read first)

- Read `CLAUDE.md` in the repo root. Its two traps are binding: no
  `parser.set_defaults()` for the global flags (defaults go in `GLOBAL_DEFAULTS`,
  applied in `parse_args()`), and never filter dubs on `version == "nlnl"`.
- `render.py` stays the only place output is formatted, JSON included.
- UI strings, help text and error messages are Dutch, in the style already there.
- YAGNI. No new dependencies (stdlib + httpx only), no abstract base classes, no
  frameworks. Comments only where the reason is not obvious from the code.
- Tests are offline (`tests/conftest.py` + `FakeClient`). Run them with
  `nix develop -c pytest -q`. Baseline before you touch anything: **193 passed**.
  There is no python/jq on the PATH outside `nix develop`.
- Existing recorded fixtures are never edited. New fixtures may be added, recorded
  from the live API with the same headers as `api.py` (a few GETs only).
- A regression test has to fail without the fix. For every behaviour below that
  has an edge case, prove the test fails by temporarily breaking the code.
- Delete files with `trash-put`, not `rm`.
- **Do not commit, push, branch or stash.** Leave everything in the working tree.
- Scratch files go in the scratchpad dir given in your brief, not in the repo.

## Phase 0 -- golden baseline

Before changing anything, capture the exact stdout of every existing command
against `FakeClient` into the scratchpad (`golden/before/*.txt`): each of
`cinemas`, `programme` (2026-09-13 and 2026-09-14, helmond), `film`, `where`,
`tagged`/`arthouse`/`classics`/`pride`, `upcoming`, `search`, with and without
`--include-dubs`/`--all`. Write a small script (also in the scratchpad) that
regenerates the same set so it can be diffed later. Phase 1 must leave the diff empty.

## Phase 1 -- one result model, two renderers (no behaviour change)

Today each function in `queries.py` returns finished Markdown. `--json` needs the
same data without the layout, and the answer is **not** a second code path that
drifts: each query builds a plain result (dataclasses or dicts -- your call,
keep it small) and `render.py` turns it into Markdown **or** JSON.

- Public query signatures stay as they are and still return `str`; add a keyword
  `as_json=False` (the last step of each query picks the renderer). All existing
  tests must pass **unmodified**.
- Markdown output of every existing command is byte-identical (golden diff empty).
- JSON conventions, decided now so the phases below do not re-litigate them:
  UTF-8, `ensure_ascii=False`, `indent=2`, trailing newline, keys English
  snake_case, ordering deterministic by construction, empty results are still
  valid JSON with empty lists.
  - A screening: `date`, `start` and `end` as local ISO datetimes
    (`"2026-09-13T19:00"`), `hall`, `formats` (the same display labels Markdown
    uses), `version`, `notes`, `booking_url` (`null` when absent). `booking_url`
    is **always** present in JSON, whether or not `--links` was given.
  - A film: `slug`, `title`, `runtime_min` (int or null), `rating`, `genres`,
    `directors`, `strands`.
  - The prose notes become data: dropped titles/screenings under `filtered`,
    the "ook gevonden" hits under `also_found` (`[{title, slug}]`).
- `--json` is a **global** flag, following the exact SUPPRESS / `GLOBAL_DEFAULTS`
  pattern, so `pathe --json programme` and `pathe programme --json` both work.
  Add tests for both positions. It applies to every command, including the new ones.
- Errors still go to stderr with exit 2, JSON mode or not.

## Phase 2 -- features

Do them in this order; each lands with its tests, Markdown and JSON.

### 2.1 Screening data

`Screening` (`catalogue.py`) gains `booking_url` (from `refCmd`, `""` if absent) and
full start/end datetimes alongside the existing `start`/`end` `HH:MM` strings. The
full datetime is needed because `parse_screenings` currently truncates `endTime`
to `HH:MM` and loses the date: a 22:00 film ending 00:40 must not look like it
ends at 00:40 *today*. (All 52 recorded showtimes have `refCmd` and `endTime`.)

### 2.2 `--links`

On `programme`, `film`, `tagged`, `arthouse`, `pride`, `classics` and `new` -- the
commands that print screening rows. Not on `where`/`upcoming`/`search`/`cinemas`/
`info`/`cinema` (they have no screenings; argparse rejecting it there is fine).
Off by default: with the flag absent the output is byte-identical to today. With
it, each screening row ends with its booking URL (plain URL, no Markdown link
syntax, so it copies cleanly). Keep the columns aligned. A screening without a
URL just gets no link.

### 2.3 `--starts-after HH:MM` and `--ends-before HH:MM`

Same commands as `--links`. Both optional, combinable. Deliberately **not**
`--starts-before`/`--ends-after`: the user rejected "starts before 15:00" because
a 90-minute film and a 3-hour one differ in when they end.

- Parsed by an argparse `type=` that accepts `19:00`, `9:30`, `19`, and `24:00`
  (meaning end of that day); anything else raises `argparse.ArgumentTypeError`
  with a Dutch message in the style of `_parse_date`'s.
- Semantics use the full datetimes from 2.1, on the screening's own date:
  `--starts-after T` keeps start >= T; `--ends-before T` keeps end <= T. So a
  22:00--00:40 screening fails `--ends-before 23:30`. If a screening has no end
  time it cannot satisfy `--ends-before` and is dropped.
- Applied after showtimes are fetched (the matrix has no times). Cells left with
  no screenings disappear, as they already do.
- Nothing vanishes silently: extend the `gefilterd:` line with a count, e.g.
  `12 voorstellingen buiten het tijdvenster`. Extend `Filtered` rather than
  inventing a second mechanism, and mind `__bool__`/`summary()`.
- `film` has its dub/kids filters off by default, but the time filters still apply
  when given.
- Tests: boundaries (exactly at T), the past-midnight case above, both flags
  together, the error message, and that a time filter without the flag changes nothing.

### 2.4 `pathe new`

Screenings of films Pathé flags `isNew` in `/api/shows` (add `is_new` to `Film`).
In the live data `isNew` means "released in roughly the last week" (11 titles with
showtimes on 2026-11-20, releaseAt 11-19 to 11-23), so:

- **Default `--days 7`**, not 60. Every (film, cinema, date) cell costs a showtimes
  request, and a new blockbuster is on daily; 60 days would be thousands of calls.
  `--from` as on the other strands.
- Same shape as `tagged`/`arthouse`: per cinema, date-major. Prefer generalising
  `tagged` to take a predicate over adding a near-copy. Heading `Nieuw — <cinema>`.
- Dub and kids filters on by default, `--include-dubs`/`--include-kids`/`--all`
  work, `--links` and the time filters work, `--json` works.
- Not a `tagged` alias: `pathe tagged new` is not required.

### 2.5 `pathe info <title>`

First search hit (same resolution as `film`/`where`, including the "ook gevonden"
note), then `PatheClient.show(slug)` -- already written, never called. No cinema
resolution and no showtimes, so it dispatches early like `search`. Print: title,
`film_line`, director(s), cast (`actors`), original title when it differs,
release date, content warnings (`cinechecks[].description`), the synopsis as
plain text (strip HTML tags, `html.unescape`; put the helper in `render.py` and
reuse it in 2.6), and one trailer URL (prefer language `nl`, else the first).
Skip the wishlist/emotion counts and `extraInformation` -- noise.
`FakeClient` gets a `show()` serving a new fixture; record 1--2 real ones from the
live API (`/api/show/<slug>`), using slugs present in `tests/fixtures/shows.json`,
for example `spider-man-brand-new-day-48103`. Find out what the live API does for
an unknown slug and make sure the user sees a readable error or empty-result
message, never a traceback.

### 2.6 `pathe cinema <slug>`

Detail for one cinema from the `/api/cinemas` payload already fetched (no extra
request). The slug is positional and resolves like `-c` does (`helmond` or
`pathe-helmond`); unknown slug gives the same `onbekende bioscoop` error. Dispatch
early like `cinemas`. Print: name, street + postcode + city (`theaters[]`), zalen
and stoelen counts, formats, wheelchair/PMR info (`hasPmrService`), each service
(`services[]`: label, plain-text description via the 2.5 helper, marking
`isAccessibility` ones), and `googleMyBusinessUrl` when present. Skip the
marketing `description`. A cinema with several `theaters` entries prints each.
Tests use `tests/fixtures/cinemas.json`.

### 2.7 CLI plumbing

`--links` and the time flags live in a `_screening_flags()` parent built fresh per
subparser (same aliasing reason as `_global_flags()`). Their defaults are applied
the ordinary way for subcommand-local flags; do not touch `set_defaults` on shared
actions. Re-run the existing regression test for the `set_defaults` trap.

## Phase 3 -- docs

- `EPILOG` in `cli.py` is the user documentation: add `new`, `info`, `cinema`,
  `--links`, the two time flags (with the "ends vs starts" reasoning in one line),
  `--json`, and examples. Keep the Dutch.
- `README.md`: same, plus a short "JSON" section giving the screening and film
  shapes from Phase 1.
- `CLAUDE.md`: update the test count, the "seven operations" wording (also in the
  `queries.py` docstring), what `render.py` now does (Markdown and JSON), and the
  common-calls list. Keep "Print it as-is" and its reasoning; add that `--json` is
  there for composing with other tools, not a reason to reformat the Markdown.
- Leave `UPSTREAM-TODO.md` and the nix files alone.

## Done means

1. `nix develop -c pytest -q` passes; the new test count is reported.
2. Phase 0 golden diff is empty for every existing command with none of the new
   flags (re-run after Phase 2 too: `--json` and the new flags are off there).
3. `ruff` clean if the repo configures it (`nix develop -c ruff check .`).
4. Live smoke test, small fanout only (`-c helmond`, today/tomorrow):
   `pathe programme --links`, `pathe film <something> --starts-after 18:00 --ends-before 23:00`,
   `pathe new -c helmond`, `pathe info <title>`, `pathe cinema helmond`,
   `pathe --json programme -c helmond` piped through a JSON parser.
5. Final report: per phase what changed, the verification commands you ran and
   their results, every judgment call you made that this plan did not decide,
   and anything not done. Do not report something as working that you did not run.
