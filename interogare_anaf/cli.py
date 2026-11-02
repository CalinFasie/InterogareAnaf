"""CLI comun: init-db, import-cui, run (docs/SPEC.md sectiunea 4)."""

import argparse
import datetime
import sqlite3

from . import anaf
from . import database
from . import engine


def _cmd_init_db(args):
    try:
        database.init_db(args.db)
    except (OSError, sqlite3.Error) as error:
        print("init-db a esuat: " + str(error))
        return 1
    print("Baza initializata: " + str(args.db))
    return 0


def _cmd_import_cui(args):
    try:
        database.import_csv(args.db, args.input)
    except database.MissingDbError as error:
        print(str(error))
        return 2
    except database.CsvError as error:
        print("import-cui: " + str(error))
        return 1
    except (OSError, sqlite3.Error) as error:
        print("import-cui a esuat: " + str(error))
        return 1
    return 0


def _cmd_run(args):
    try:
        datetime.date.fromisoformat(args.date)
    except ValueError:
        print("run: --date trebuie sa fie in format YYYY-MM-DD (primit: "
              + repr(args.date) + ").")
        return 2
    try:
        return engine.execute_run(
            args.db,
            args.date,
            args.api_url,
            args.timeout,
            args.only_missing,
        )
    except database.MissingDbError as error:
        print(str(error))
        return 2
    except (OSError, sqlite3.Error) as error:
        print("run a esuat: " + str(error))
        return 1


def build_parser():
    parser = argparse.ArgumentParser(
        prog="interogare_anaf",
        description="Interogarea ANAF TVA v9 pentru CUI-uri din SQLite.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    parser_init = subparsers.add_parser(
        "init-db", help="creeaza/actualizeaza schema SQLite (fara apeluri ANAF)"
    )
    parser_init.add_argument("--db", required=True, help="calea catre fisierul SQLite")
    parser_init.set_defaults(func=_cmd_init_db)

    parser_import = subparsers.add_parser(
        "import-cui", help="popularea initiala din CSV (fara apeluri ANAF)"
    )
    parser_import.add_argument("--db", required=True, help="calea catre fisierul SQLite")
    parser_import.add_argument(
        "--input",
        required=True,
        help="CSV UTF-8 cu antetul cui;denumire_initiala",
    )
    parser_import.set_defaults(func=_cmd_import_cui)

    parser_run = subparsers.add_parser("run", help="interogheaza ANAF si actualizeaza SQLite")
    parser_run.add_argument("--db", required=True, help="calea catre fisierul SQLite")
    parser_run.add_argument(
        "--date", required=True, help="data calendaristica reala YYYY-MM-DD"
    )
    parser_run.add_argument(
        "--api-url",
        default=anaf.DEFAULT_API_URL,
        help="endpoint ANAF (valoare implicita: endpointul oficial; "
             "foloseste un URL local doar pentru testare explicita)",
    )
    parser_run.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="timeout pe cerere, in secunde (implicita: 20)",
    )
    parser_run.add_argument(
        "--only-missing",
        action="store_true",
        help="selecteaza doar CUI-urile cu denumire_anaf IS NULL",
    )
    parser_run.set_defaults(func=_cmd_run)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
