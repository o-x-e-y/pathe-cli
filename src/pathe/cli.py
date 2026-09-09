"""Command line entry point.

Exists to answer "what is on, and is it worth going to" without opening a
browser that wants to sell you a seat. Four questions drive the design: the
day's programme at the cinemas actually in reach, when a specific film plays
over the coming weeks, when the arthouse and Pride Night strands land, and what
classics are being dug out -- the last two being things you have to seek out,
because unlike a wide release they play once and vanish.

Read-only. No key, no login, no booking: every endpoint used is an
unauthenticated GET on www.pathe.nl/api, and nothing here can reserve a seat.

Two things the API gets right that the design leans on. Projection format is a
property of the *screening*, not the film -- the same title plays 4DX at 11:00
and flat at 20:00 -- so formats are printed per row, not per title. And the
cinema matrix covers the whole horizon in one request while already carrying
tags, versions and the kids flag, so filtering happens before any showtime is
fetched and a day's programme costs a few dozen requests rather than a few
hundred.
"""

import argparse
import asyncio
import datetime as dt
import sys

from . import queries
from .api import PatheClient, PatheError
from .cache import Cache
from .catalogue import date_range
from .config import (
    DEFAULT_HORIZON_DAYS,
    default_cinemas,
    resolve,
)
from .config import favorites as configured_favorites

STRAND_ALIASES = {
    "arthouse": "in-the-picture",
    "inthepicture": "in-the-picture",
    "itp": "in-the-picture",
    "pride": "pridenight",
    "classic": "classics",
    "ladies": "ladiesnight",
    "horror": "horrornight",
    "sneak": "sneaknight",
    "opera": "operaencore",
}


def _today():
    return dt.date.today().isoformat()


def _parse_date(value):
    """Accepts an ISO date, `today`/`vandaag`, `tomorrow`/`morgen`, or `+N`."""
    if value in (None, "", "today", "vandaag"):
        return _today()
    if value in ("tomorrow", "morgen"):
        return (dt.date.today() + dt.timedelta(days=1)).isoformat()
    if value.startswith("+") and value[1:].isdigit():
        return (dt.date.today() + dt.timedelta(days=int(value[1:]))).isoformat()
    try:
        return dt.date.fromisoformat(value).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"onbegrijpelijke datum: {value!r} (verwacht JJJJ-MM-DD, today, tomorrow of +N)"
        )


EPILOG = """\
bioscopen (default: je favorieten, anders helmond, eindhoven, tilburg-centrum,
           tilburg-stappegoor)
  -c neemt slugs met of zonder `pathe-` prefix, komma-gescheiden.
  -f gebruikt je favorieten uit ~/.config/pathe/settings.json, ook als
     PATHE_CINEMAS gezet is. -c en -f samen is een fout.
  `pathe cinemas` toont alle 31 met de formaten die ze hebben.
  Volgorde: -c  >  PATHE_CINEMAS  >  settings.json  >  ingebouwde vier.

  settings.json ziet er zo uit:
    { "favorites": ["helmond", "tilburg-stappegoor"] }

programmalijnen (`tagged`, of de aliassen)
  arthouse   in-the-picture   zo/ma, ~19:00, wisselt per twee weken: A op
                              zondag en B op maandag, daarna B op zondag en
                              A op maandag; draait in ~20 bioscopen tegelijk
  pride      pridenight       woensdag, ~maandelijks, enkele bioscopen
  classics   classics         heruitgaves, spelen kort -- daarom een eigen lijst
  ook geldig: ladiesnight horrornight sneaknight operaencore ballet music
              theater docs bollywood soundsessions kleuter 50Plus

filters (standaard AAN, behalve bij `film`)
  Nagesynchroniseerde versies van buitenlandse films en kinderfilms worden
  weggelaten; wat wegviel staat onderaan achter `gefilterd:`. Een dub wordt
  herkend aan de titel -- (NL), (Nederlands gesproken), (Nederlandse versie) --
  en niet aan de taalcode: Nederlandstalige eigen producties als André Rieu of
  Golden Earring Live zijn ook `nlnl` en horen juist te blijven staan.
  --include-dubs / --include-kids / --all zetten ze uit.
  `film` filtert niet: als je een titel met naam opvraagt bedoel je die titel.

formaten
  Per voorstelling, niet per film: IMAX 4DX 3D ScreenX Dolby Atmos/Cinema.
  Een regel zonder formaat (—) is een gewone digitale vertoning.

datums
  JJJJ-MM-DD, `today`/`vandaag`, `tomorrow`/`morgen`, of `+N` dagen.
  --days bepaalt het venster vooruit (default 60; pride 90). Pathé publiceert
  ~10 maanden vooruit, maar die staart is vrijwel alleen opera en ballet.

cache
  Catalogus 6 u, speeltijden 30 min, onder ~/.cache/pathe.
  --no-cache omzeilt, --clear-cache leegt.

voorbeelden
  pathe programme                        vanavond, alle vier de bioscopen
  pathe programme tomorrow -c helmond
  pathe film dune --days 30              wanneer draait Dune bij jou
  pathe where leviticus                  in welke bioscopen draait het
  pathe where leviticus -f               alleen die van jou
  pathe arthouse                         de zo/ma arthouse-cyclus
  pathe pride                            eerstvolgende Pride Nights
  pathe classics -c eindhoven,helmond
  pathe upcoming --limit 40
"""
# Values for the global flags when given on neither side of the subcommand.
# Applied after parsing rather than through `set_defaults`, because
# `set_defaults` mutates `action.default` in place -- and since `parents=[...]`
# shares action *objects*, that would turn off the SUPPRESS below and let each
# subparser overwrite a flag given before the subcommand.
GLOBAL_DEFAULTS = {
    "cinemas": None,
    "favorites": False,
    "no_cache": False,
    "clear_cache": False,
    "include_dubs": False,
    "include_kids": False,
    "all": False,
}


def _global_flags():
    """A fresh parser each call. Sharing one instance across the top level and
    every subparser would share the action objects too, which is exactly the
    aliasing bug the comment above describes.

    Every default is SUPPRESS, so an unset flag is absent from the namespace
    instead of present-and-false; that is what lets a value given before the
    subcommand survive the subparser's own parse.
    """
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--cinemas", "-c", default=argparse.SUPPRESS,
                   help="komma-gescheiden slugs (default: config)")
    p.add_argument("--favorites", "-f", action="store_true", default=argparse.SUPPRESS,
                   help="gebruik je favorieten uit settings.json")
    p.add_argument("--no-cache", action="store_true", default=argparse.SUPPRESS,
                   help="negeer de schijfcache")
    p.add_argument("--clear-cache", action="store_true", default=argparse.SUPPRESS,
                   help="leeg de cache en stop")
    p.add_argument("--include-dubs", action="store_true", default=argparse.SUPPRESS,
                   help="toon nagesynchroniseerde versies")
    p.add_argument("--include-kids", action="store_true", default=argparse.SUPPRESS,
                   help="toon kinderfilms")
    p.add_argument("--all", action="store_true", default=argparse.SUPPRESS,
                   help="geen filters (dubs + kinderfilms)")
    return p


def build_parser():
    parser = argparse.ArgumentParser(
        prog="pathe",
        parents=[_global_flags()],
        description="Programma-informatie uit de publieke Pathé API. Read-only, geen login.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    def add(name, help):
        # Attaching the global flags here too is what makes the natural
        # `pathe programme -c helmond` work as well as `pathe -c helmond programme`.
        return sub.add_parser(name, parents=[_global_flags()], help=help,
                              formatter_class=argparse.RawDescriptionHelpFormatter)

    add("cinemas", "alle Pathé-bioscopen met hun formaten")

    p = add("programme", "programma van een dag")
    p.add_argument("date", nargs="?", default="today", help="JJJJ-MM-DD, today, tomorrow, +N")

    p = add("film", "speeltijden van één film over een periode")
    p.add_argument("query", help="titel (of deel daarvan)")
    p.add_argument("--days", type=int, default=DEFAULT_HORIZON_DAYS)
    p.add_argument("--from", dest="start", default="today")

    p = add("where", "in welke bioscopen een film draait")
    p.add_argument("query", help="titel (of deel daarvan)")
    p.add_argument("--days", type=int, default=DEFAULT_HORIZON_DAYS)
    p.add_argument("--from", dest="start", default="today")

    p = add("tagged", "programmalijn: arthouse, pride, classics, ...")
    p.add_argument("tag")
    p.add_argument("--days", type=int, default=DEFAULT_HORIZON_DAYS)
    p.add_argument("--from", dest="start", default="today")

    for name, days in (("arthouse", DEFAULT_HORIZON_DAYS), ("pride", 90),
                       ("classics", DEFAULT_HORIZON_DAYS)):
        p = add(name, f"alias voor `tagged {name}`")
        p.add_argument("--days", type=int, default=days)
        p.add_argument("--from", dest="start", default="today")

    p = add("upcoming", "binnenkort in de bioscoop")
    p.add_argument("--limit", type=int, default=25)

    p = add("search", "zoek een film in de catalogus")
    p.add_argument("query")

    return parser


def parse_args(argv=None):
    args = build_parser().parse_args(argv)
    for name, value in GLOBAL_DEFAULTS.items():
        args.__dict__.setdefault(name, value)
    return args
async def _dispatch(args, client):
    flags = {
        "include_dubs": args.include_dubs or args.all,
        "include_kids": args.include_kids or args.all,
    }
    command = args.command

    # Commands that never touch a cinema answer before the slug lookup, so
    # `pathe upcoming` stays a single request.
    if command == "cinemas":
        return await queries.list_cinemas(client)
    if command == "search":
        return await queries.find_film(client, args.query)
    if command == "upcoming":
        return await queries.upcoming(client, args.limit, include_dubs=flags["include_dubs"])

    if args.cinemas and args.favorites:
        raise PatheError("kies `-c` of `-f`, niet allebei")
    if args.favorites:
        requested = configured_favorites()
    elif args.cinemas:
        requested = args.cinemas.split(",")
    else:
        requested = default_cinemas()
    known = [c["slug"] for c in await client.cinemas()]
    cinemas, unknown = resolve(requested, known)
    if unknown:
        raise PatheError(
            f"onbekende bioscoop: {', '.join(unknown)} (zie `pathe cinemas`)"
        )
    if not cinemas:
        raise PatheError("geen bioscopen opgegeven")

    if command == "programme":
        return await queries.programme(client, cinemas, _parse_date(args.date), **flags)
    if command == "film":
        dates = date_range(args.days, dt.date.fromisoformat(_parse_date(args.start)))
        return await queries.film_showtimes(client, args.query, cinemas, dates)
    if command == "where":
        # `where` reuses the resolved set as its "Jouw bioscopen" list, so
        # `-c breda,nijmegen` asks the same question about a different pair.
        dates = date_range(args.days, dt.date.fromisoformat(_parse_date(args.start)))
        return await queries.where(client, args.query, cinemas, dates,
                                   only_favorites=args.favorites)
    if command in ("tagged", "arthouse", "pride", "classics"):
        tag = {
            "arthouse": "in-the-picture",
            "pride": "pridenight",
            "classics": "classics",
        }.get(command) or STRAND_ALIASES.get(args.tag.lower(), args.tag)
        dates = date_range(args.days, dt.date.fromisoformat(_parse_date(args.start)))
        return await queries.tagged(client, tag, cinemas, dates, **flags)
    raise AssertionError(f"unhandled command {command!r}")
async def _run(args):
    cache = Cache(enabled=not args.no_cache)
    async with PatheClient(cache=cache) as client:
        return await _dispatch(args, client)


def main(argv=None):
    parser = build_parser()
    args = parse_args(argv)

    if args.clear_cache:
        print(f"cache geleegd: {Cache().clear()} bestanden")
        return 0
    if not args.command:
        parser.print_help()
        return 1
    try:
        sys.stdout.write(asyncio.run(_run(args)))
    except PatheError as exc:
        print(f"pathe: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
