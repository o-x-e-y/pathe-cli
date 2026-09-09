# pathe-cli

Read-only CLI for the public Pathé Nederland programme API. Prints Markdown you
can paste somewhere.

```
$ pathe arthouse -c helmond --days 21
## In the Picture — Pathé Helmond

**zondag 13 september 2026** — Fuori
115 min · -12 jaar · OV · Drama
  18:45–21:00  —  zaal 1

**maandag 14 september 2026** — Primavera
110 min · -12 jaar · OV · Biografie, Drama
  19:00–21:10  —  zaal 3
```

## What it does

| command | |
|---|---|
| `pathe programme [date]` | the day's programme |
| `pathe film <titel>` | where and when one film plays |
| `pathe arthouse` | the In the Picture strand (zo/ma, ~19:00, wisselt per twee weken) |
| `pathe pride` | Pride Night (woensdag, ~maandelijks) |
| `pathe classics` | heruitgaves — they play briefly, so they get their own list |
| `pathe tagged <tag>` | any other strand: `ladiesnight`, `horrornight`, `operaencore`, ... |
| `pathe upcoming` | coming soon |
| `pathe search <titel>` | find a title and its slug |
| `pathe cinemas` | all 31, with the formats each one has |

`pathe --help` documents the strands, the filters and the date syntax in full.

## Notes

**No account, no key, no booking.** Every endpoint used is an unauthenticated
`GET` on `www.pathe.nl/api`. Nothing here can reserve a seat.

**Format is per screening, not per film.** The same title plays 4DX at 15:15 and
flat at 20:15, so IMAX / 4DX / 3D / ScreenX / Dolby are printed on the row, and
the header lists what the day offers. A `—` is a plain digital screening.

**Dubs and kids' films are filtered by default**, and what went is listed after
`gefilterd:`. A dub is recognised by its title — `(NL)`,
`(Nederlands gesproken)`, `(Nederlandse versie)` — and *not* by the `nlnl`
language code, because Dutch-language originals like André Rieu and Golden
Earring Live are `nlnl` too and should stay. `--include-dubs`, `--include-kids`
and `--all` turn the filters off; `pathe film` never filters, since asking for a
title by name means that title.

**Default cinemas** are Helmond, Eindhoven, Tilburg Centrum and Tilburg
Stappegoor. Override per call with `-c`, or globally with `PATHE_CINEMAS`.

**Caching.** Catalogue 6 h, showtimes 30 min, under `~/.cache/pathe`. A cold
four-cinema day costs ~5 s; the same query again is instant. `--no-cache` skips
it, `--clear-cache` empties it.

## Install

```nix
{
  inputs.pathe-cli.url = "github:oxey/pathe-cli";

  # then either
  environment.systemPackages = [ inputs.pathe-cli.packages.${system}.default ];
  # or via the overlay
  nixpkgs.overlays = [ inputs.pathe-cli.overlays.default ];
}
```

```sh
nix run .            # without installing
nix develop          # dev shell; src/ is already on PYTHONPATH
pytest               # 139 tests, fully offline
```

## Why the fanout stays small

Pathé has no bulk-showtimes endpoint, and `?date=` on the cinema endpoint is
silently ignored. But `/api/cinema/<slug>/shows` returns the **entire** horizon
in one request, and every cell already carries its tags, language versions and
kids flag. So filtering happens on that matrix, before any showtime request, and
only surviving cells cost a round trip — no date is ever polled blindly. A
strand query like `arthouse` touches a handful of cells; `upcoming` needs no
fanout at all.
