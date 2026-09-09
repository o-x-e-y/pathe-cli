# pathe-cli

Read-only CLI over the public Pathé Nederland API. Use it instead of fetching
`pathe.nl` yourself — it handles the fanout, the filtering and the formatting.

## Using it

Run `pathe --help` first: it documents every strand tag, the filter rules, the
date syntax and the cinema slugs, and it is kept current with the code.

Output is Markdown, formatted by the tool. **Print it as-is.** Do not reformat,
re-sort or re-summarise it into your own layout — deterministic output is the
reason formatting lives in `render.py` rather than being left to a model, and
the user relies on being able to copy it verbatim.

Common calls:

```sh
pathe programme                       # tonight, default four cinemas
pathe programme +3 -c eindhoven
pathe film "dune" --days 30
pathe where "leviticus"               # which cinemas have it -- one request
pathe arthouse                        # In the Picture, zo/ma
pathe pride
pathe classics -c helmond,eindhoven
pathe upcoming --limit 40
```

Flags work on either side of the subcommand.

`where` answers *where*, `film` answers *when*. For "where can I see X" run
`where` first -- one request, only the cinemas that have it -- then `film -c
<the ones that matter>`. Never answer a "where" question by passing all 31
slugs to `film`.

Favourites live in `~/.config/pathe/settings.json` (`{"favorites": [...]}`),
written by the home-manager module the flake exports. `-f` selects them even
when `PATHE_CINEMAS` is set.

## What it cannot do

No login, no account, no seat booking — every endpoint is an unauthenticated
GET. If asked to order tickets, say that this tool cannot and point at the
`refCmd` booking URL in the API, or at pathe.nl.

## Layout

| file | |
|---|---|
| `api.py` | httpx client, bounded concurrency, retries |
| `cache.py` | two-tier TTL disk cache (catalogue 6 h, showtimes 30 min) |
| `catalogue.py` | joins `/api/shows` metadata to a cinema's date matrix |
| `filters.py` | the dub and kids rules, and what they report |
| `tags.py` | tag vocabulary → display labels |
| `render.py` | **the only** place output is formatted |
| `queries.py` | the seven operations, each returning finished Markdown |
| `cli.py` | argparse surface; the `--help` epilog is the user documentation |

## Working on it

`nix develop` then `pytest`. The suite is 177 tests and entirely offline —
`tests/conftest.py` serves fixtures recorded from the live API on 2026-09-09.
Re-record by fetching the same paths if the shapes change.

Two traps worth knowing:

- **Do not call `parser.set_defaults()` for the global flags.** `parents=[...]`
  shares action *objects*, and `set_defaults` mutates `action.default` in place,
  which breaks `SUPPRESS` and lets a subparser silently clobber a flag given
  before the subcommand. Defaults are applied post-parse in `parse_args()`.
  There is a regression test.
- **Do not filter on `version == "nlnl"`.** That is a language code, not a dub
  marker; André Rieu and Golden Earring Live are Dutch originals. Match the
  title marker instead. There is a test asserting exactly the eight real dubs.
