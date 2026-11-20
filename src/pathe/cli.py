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
import re
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


def _parse_date(value, today=None):
    """Accepts an ISO date, `MM-DD`, `DD`, `today`/`vandaag`, `tomorrow`/`morgen`, or `+N`."""
    today = today or dt.date.today()
    try:
        return _date_from(value, today).isoformat()
    except ValueError:
        pass
    message = (f"onbegrijpelijke datum: {value!r} "
               "(verwacht JJJJ-MM-DD, MM-DD, DD, today, tomorrow of +N)")
    swapped = "-".join(reversed(value.split("-")))
    try:
        message += f"; bedoel je {_date_from(swapped, today).isoformat()}?"
    except ValueError:
        pass
    raise argparse.ArgumentTypeError(message)


def _parse_time(value):
    """`19:00`, `9:30` or `19` as a timedelta after midnight. `24:00` is the
    end of the day, which a `datetime.time` cannot hold."""
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?", value.strip())
    if m:
        hours, minutes = int(m[1]), int(m[2] or 0)
        if (hours < 24 and minutes < 60) or (hours, minutes) == (24, 0):
            return dt.timedelta(hours=hours, minutes=minutes)
    raise argparse.ArgumentTypeError(
        f"onbegrijpelijke tijd: {value!r} (verwacht UU:MM, U:MM of UU, van 0:00 tot 24:00)"
    )


def _date_from(value, today):
    if value in (None, "", "today", "vandaag"):
        return today
    if value in ("tomorrow", "morgen"):
        return today + dt.timedelta(days=1)
    if value.startswith("+") and value[1:].isdigit():
        return today + dt.timedelta(days=int(value[1:]))
    if m := re.fullmatch(r"(\d{1,2})", value):
        date = today.replace(day=int(m[1]))
        if date < today:
            year, month = divmod(today.year * 12 + today.month, 12)
            date = dt.date(year, month + 1, int(m[1]))
        return date
    if m := re.fullmatch(r"(\d{1,2})-(\d{1,2})", value):
        date = dt.date(today.year, int(m[1]), int(m[2]))
        return date if date >= today else date.replace(year=today.year + 1)
    return dt.date.fromisoformat(value)


EPILOG = """\
bioscopen (default: je favorieten, anders helmond, eindhoven, tilburg-centrum,
           tilburg-stappegoor)
  -c neemt slugs met of zonder `pathe-` prefix, komma-gescheiden.
  -f gebruikt je favorieten uit ~/.config/pathe/settings.json, ook als
     PATHE_CINEMAS gezet is. -c en -f samen is een fout.
  `pathe cinemas` toont alle 31 met de formaten die ze hebben, `pathe cinema
  helmond` het adres, de zalen en de voorzieningen van één.
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
  Het tijdvenster hieronder geldt wel bij `film`, als je het opgeeft.

voorstellingen (programme, film, tagged, arthouse, pride, classics, new)
  --links               de boekingslink achter elke voorstelling, als kale URL
                        zodat hij goed kopieert. Boeken doet deze tool niet.
  --starts-after UU:MM  alleen wat om of na UU:MM begint
  --ends-before UU:MM   alleen wat om of voor UU:MM afgelopen is
  Tijden als 19:00, 9:30, 19 of 24:00 (einde van de dag), op de dag van de
  voorstelling: 22:00–00:40 eindigt morgen en valt dus buiten --ends-before
  23:30. Geen --starts-before: of je op tijd thuis bent hangt af van wanneer
  de film afloopt, en 90 minuten of 3 uur maakt daar alles uit.
  Wat buiten het venster valt, telt mee achter `gefilterd:`.

nieuw, info
  `pathe new` toont de films die Pathé als nieuw markeert -- in de praktijk
  uitgebracht in ongeveer de laatste week -- per bioscoop, met de filters aan.
  `pathe info <titel>` geeft regie, cast, Kijkwijzer, synopsis en trailer.

json
  --json (voor of na het commando, bij elk commando) geeft dezelfde gegevens
  als JSON, om door te geven aan andere tools. Een voorstelling heeft date,
  start, end (JJJJ-MM-DDTUU:MM), hall, formats, version, notes en booking_url --
  die altijd, ook zonder --links, en null als Pathé er geen heeft. Wat wegviel
  staat onder `filtered`, andere treffers onder `also_found`. Fouten blijven
  op stderr, met exitcode 2.

formaten
  Per voorstelling, niet per film: IMAX 4DX 3D ScreenX Dolby Atmos/Cinema.
  Een regel zonder formaat (—) is een gewone digitale vertoning.

datums
  JJJJ-MM-DD, MM-DD, DD, `today`/`vandaag`, `tomorrow`/`morgen`, of `+N` dagen.
  MM-DD is dit jaar, of volgend jaar als die datum al voorbij is; DD is deze
  maand, of volgende maand. Vandaag telt niet als voorbij.
  --days bepaalt het venster vooruit (default 60; pride 90; new 7). Pathé
  publiceert ~10 maanden vooruit, maar die staart is vrijwel alleen opera en
  ballet.

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
  pathe programme -c helmond --links     met boekingslinks
  pathe film dune --starts-after 18:00 --ends-before 23:00
  pathe new -c helmond                   wat er deze week nieuw is
  pathe info dune                        regie, cast, synopsis, trailer
  pathe cinema helmond                   adres, zalen, voorzieningen
  pathe --json programme -c helmond      hetzelfde, als JSON
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
    "json": False,
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
    p.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                   help="JSON in plaats van Markdown")
    return p


def _screening_flags():
    """For the commands that print screening rows. Fresh per subparser for the
    same reason as `_global_flags`; these exist only after the subcommand, so
    their defaults are ordinary ones."""
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--links", action="store_true",
                   help="boekingslink achter elke voorstelling")
    p.add_argument("--starts-after", type=_parse_time, metavar="UU:MM",
                   help="alleen voorstellingen die om of na UU:MM beginnen")
    p.add_argument("--ends-before", type=_parse_time, metavar="UU:MM",
                   help="alleen voorstellingen die om of voor UU:MM afgelopen zijn")
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

    def add(name, help, screenings=False):
        # Attaching the global flags here too is what makes the natural
        # `pathe programme -c helmond` work as well as `pathe -c helmond programme`.
        parents = [_global_flags(), *([_screening_flags()] if screenings else [])]
        return sub.add_parser(name, parents=parents, help=help,
                              formatter_class=argparse.RawDescriptionHelpFormatter)

    add("cinemas", "alle Pathé-bioscopen met hun formaten")

    p = add("cinema", "adres, zalen en voorzieningen van één bioscoop")
    p.add_argument("slug", help="bioscoop, met of zonder `pathe-`")

    p = add("programme", "programma van een dag", screenings=True)
    p.add_argument("date", nargs="?", default="today", help="JJJJ-MM-DD, MM-DD, DD, today, tomorrow, +N")

    p = add("film", "speeltijden van één film over een periode", screenings=True)
    p.add_argument("query", help="titel (of deel daarvan)")
    p.add_argument("--days", type=int, default=DEFAULT_HORIZON_DAYS)
    p.add_argument("--from", dest="start", default="today")

    p = add("where", "in welke bioscopen een film draait")
    p.add_argument("query", help="titel (of deel daarvan)")
    p.add_argument("--days", type=int, default=DEFAULT_HORIZON_DAYS)
    p.add_argument("--from", dest="start", default="today")

    p = add("tagged", "programmalijn: arthouse, pride, classics, ...", screenings=True)
    p.add_argument("tag")
    p.add_argument("--days", type=int, default=DEFAULT_HORIZON_DAYS)
    p.add_argument("--from", dest="start", default="today")

    for name, days in (("arthouse", DEFAULT_HORIZON_DAYS), ("pride", 90),
                       ("classics", DEFAULT_HORIZON_DAYS)):
        p = add(name, f"alias voor `tagged {name}`", screenings=True)
        p.add_argument("--days", type=int, default=days)
        p.add_argument("--from", dest="start", default="today")

    p = add("new", "films die net uit zijn (Pathé's `isNew`)", screenings=True)
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--from", dest="start", default="today")

    p = add("upcoming", "binnenkort in de bioscoop")
    p.add_argument("--limit", type=int, default=25)

    p = add("search", "zoek een film in de catalogus")
    p.add_argument("query")

    p = add("info", "regie, cast, synopsis en trailer van één film")
    p.add_argument("query", help="titel (of deel daarvan)")

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
    as_json = args.json

    # Commands that never touch a cinema answer before the slug lookup, so
    # `pathe upcoming` stays a single request.
    if command == "cinemas":
        return await queries.list_cinemas(client, as_json=as_json)
    if command == "search":
        return await queries.find_film(client, args.query, as_json=as_json)
    if command == "info":
        return await queries.film_info(client, args.query, as_json=as_json)
    if command == "upcoming":
        return await queries.upcoming(client, args.limit, include_dubs=flags["include_dubs"],
                                      as_json=as_json)
    if command == "cinema":
        found, unknown = resolve([args.slug], [c["slug"] for c in await client.cinemas()])
        if unknown or not found:
            raise PatheError(f"onbekende bioscoop: {args.slug} (zie `pathe cinemas`)")
        return await queries.cinema_info(client, found[0], as_json=as_json)

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

    shown = {
        "links": getattr(args, "links", False),
        "starts_after": getattr(args, "starts_after", None),
        "ends_before": getattr(args, "ends_before", None),
        "as_json": as_json,
    }
    if command == "programme":
        return await queries.programme(client, cinemas, _parse_date(args.date), **flags, **shown)
    if command == "film":
        dates = date_range(args.days, dt.date.fromisoformat(_parse_date(args.start)))
        return await queries.film_showtimes(client, args.query, cinemas, dates, **shown)
    if command == "where":
        # `where` reuses the resolved set as its "Jouw bioscopen" list, so
        # `-c breda,nijmegen` asks the same question about a different pair.
        dates = date_range(args.days, dt.date.fromisoformat(_parse_date(args.start)))
        return await queries.where(client, args.query, cinemas, dates,
                                   only_favorites=args.favorites, as_json=as_json)
    if command in ("tagged", "arthouse", "pride", "classics"):
        tag = {
            "arthouse": "in-the-picture",
            "pride": "pridenight",
            "classics": "classics",
        }.get(command) or STRAND_ALIASES.get(args.tag.lower(), args.tag)
        dates = date_range(args.days, dt.date.fromisoformat(_parse_date(args.start)))
        return await queries.tagged(client, tag, cinemas, dates, **flags, **shown)
    if command == "new":
        dates = date_range(args.days, dt.date.fromisoformat(_parse_date(args.start)))
        return await queries.new(client, cinemas, dates, **flags, **shown)
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
    except (PatheError, argparse.ArgumentTypeError) as exc:
        print(f"pathe: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
