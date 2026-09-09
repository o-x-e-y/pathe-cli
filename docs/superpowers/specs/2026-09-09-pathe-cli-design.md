# pathe-cli — design

**Date:** 2026-09-09

## Problem

Get Pathé Nederland programme information without logging in or booking:
a day's programme for the cinemas in reach, when a given film plays over the
coming weeks, when the Arthouse / Pride Night strands land, which classics are
being dug out, and what is coming soon. Every film should lead with its runtime
and projection format.

## API discovery

`https://www.pathe.nl/api/*` is public, unauthenticated, and unsigned. No key,
no HMAC, no session. Endpoints used:

| endpoint | gives |
|---|---|
| `/api/cinemas` | 31 cinemas: slug, city, format tags, halls, GPS |
| `/api/shows` | 240 titles: `duration`, `genres`, `contentRating`, `type`, `isComingSoon`, `upcomingOrder` |
| `/api/show/{slug}` | synopsis, cast, trailers, all formats the title plays in |
| `/api/cinema/{slug}/shows` | date×title matrix, ~10 months, each cell tagged |
| `/api/show/{slug}/showtimes/{cinema}/{date}` | actual times, `endTime`, `version`, `tags`, hall, booking URL |

Findings that shaped the design:

- **No bulk-showtimes endpoint.** `?date=` on the cinema endpoint is silently
  ignored — the response is byte-identical with and without it.
- **The matrix is the lever.** One request per cinema covers the whole horizon
  and each cell already carries `tags`, `versions` and (per title) `isKids`. So
  filtering happens before any showtime request, and no date is ever polled
  blindly.
- **Format is per screening.** A single title returns `["3d","4dx","DEFAULT"]`
  at one time and `["DEFAULT","PAUSE"]` at another.
- **Strands are tags.** `in-the-picture`, `pridenight`, `classics`,
  `ladiesnight`, `horrornight`, `operaencore`, `ballet`, … — one mechanism.
- **The Sunday/Monday arthouse cycle is real and visible:** Sun 13 Sep *Fuori*,
  Mon 14 Sep *Primavera*, Sun 20 Sep *No Good Men*, Mon 21 Sep *Fuori*, across
  ~20 cinemas at once.
- **Dubs are separate show entries** marked in the title. `nlnl` is a language
  code, not a dub marker: André Rieu, Golden Earring Live and Maximapark are
  Dutch originals.

## Decisions

**A CLI, not an MCP server.** All the consolidation is deterministic string and
date logic with no model in the loop, so an MCP buys nothing and costs tool
schema in every session — the argument already made in `weather/default.nix`.
Agent guidance lives in a rich `--help` epilog and `CLAUDE.md` instead.

**The tool renders the Markdown.** Handing a model raw JSON means the layout is
re-invented on every call. Formatting server-side makes output byte-identical
across runs and safe to copy verbatim. One formatter in `render.py`; there is no
JSON output path to drift against.

**Lazy fanout with a two-tier disk cache.** Catalogue 6 h, showtimes 30 min,
under `~/.cache/pathe`, bounded to 6 concurrent requests. Measured: a cold
four-cinema day is ~5 s, warm ~0.14 s. Caching degrades to off rather than
failing when `HOME` is unwritable.

**Filters on by default, and transparent.** Dubs and kids' films are dropped
and named after `gefilterd:`, deduplicated across cinemas. `pathe film` does not
filter — asking for a title by name means that title.

**Default cinemas:** Helmond, Eindhoven, Tilburg Centrum, Tilburg Stappegoor.
A national sweep is ~1000 requests and answers nobody's question.

**Horizon:** 60 days (90 for Pride Night). Pathé publishes ~10 months but the
tail is almost entirely opera and ballet encores.

## Structure

`api.py` (HTTP) · `cache.py` (TTL) · `catalogue.py` (join) · `filters.py`
(rules) · `tags.py` (vocabulary) · `render.py` (output) · `queries.py`
(operations) · `cli.py` (surface).

## Testing

140 tests, entirely offline, against fixtures recorded from the live API on
2026-09-09 — including the awkward cases the filters exist for. The suite runs
in the Nix build sandbox.

Two bugs it caught that were real, not cosmetic:

1. Global flags only parsed *before* the subcommand, so `pathe programme -c
   helmond` was rejected. Cause: `parents=[...]` shares action objects and
   `set_defaults()` mutates `action.default` in place, defeating `SUPPRESS`.
2. `Cache.__init__` unconditionally `mkdir`ed, crashing where `HOME` is not
   writable.

## Packaging

Flake with `packages.default`, `devShells.default` and `overlays.default`,
mirroring `~/Repos/oxeylyzer`. `nix/package.nix` is a
`buildPythonApplication` that runs the suite during the build.
