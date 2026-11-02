"""Command line entry points for InterogareAnaf."""

import argparse
from datetime import date
import math
from pathlib import Path
import sqlite3
import sys
import uuid

from .client import (
    DEFAULT_API_URL, MAX_BATCH_SIZE, AnafClient, AttemptEvent, CuiOutcome,
    ProtocolFailure, RequestFailure, apply_payload,
)
from .storage import (
    DatabaseError, HistoryEntry, import_cui, initialize_database, load_cuis,
    persist_attempt,
)


def _positive_float(value: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("trebuie sa fie un numar") from exc
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("trebuie sa fie mai mare decat zero")
    return result


def _valid_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("data trebuie sa fie YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise argparse.ArgumentTypeError("data trebuie sa fie YYYY-MM-DD")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m interogare_anaf")
    commands = parser.add_subparsers(dest="command", required=True)

    init_parser = commands.add_parser("init-db", help="creeaza schema SQLite")
    init_parser.add_argument("--db", required=True, type=Path)

    import_parser = commands.add_parser("import-cui", help="importa CUI-uri din CSV")
    import_parser.add_argument("--db", required=True, type=Path)
    import_parser.add_argument("--input", required=True, type=Path)

    run_parser = commands.add_parser("run", help="interogheaza ANAF TVA v9 pe loturi")
    run_parser.add_argument("--db", required=True, type=Path)
    run_parser.add_argument("--date", required=True, type=_valid_date)
    run_parser.add_argument("--api-url", default=DEFAULT_API_URL)
    run_parser.add_argument("--timeout", type=_positive_float, default=20.0)
    run_parser.add_argument("--only-missing", action="store_true")
    return parser


def _run(args: argparse.Namespace) -> int:
    cuis = load_cuis(args.db, only_missing=args.only_missing)
    batches = [cuis[offset:offset + MAX_BATCH_SIZE]
               for offset in range(0, len(cuis), MAX_BATCH_SIZE)]
    run_id = str(uuid.uuid4())
    print(f"Rulare {run_id}; CUI citite din SQLite: {len(cuis)}; loturi: {len(batches)}.")
    if not batches:
        return 0

    client = AnafClient(api_url=args.api_url, timeout=args.timeout)
    totals = {"found": 0, "not_found": 0, "incomplete": 0,
              "failed": 0, "anomalies": 0, "error_records": 0}
    for index, batch in enumerate(batches, start=1):
        def record_error_attempt(event: AttemptEvent) -> None:
            entries = [HistoryEntry(
                cui=cui, rulare_id=run_id, incercat_la=event.attempted_at,
                data_interogarii=args.date, nr_lot=index, nr_incercare=event.number,
                rezultat="EROARE", http_status=event.http_status,
                cod_eroare=event.error_code, mesaj_eroare=event.error_message,
            ) for cui in batch]
            persist_attempt(args.db, entries)
            totals["error_records"] += len(entries)

        try:
            response = client.fetch(batch, args.date, on_error_attempt=record_error_attempt)
            try:
                result = apply_payload(batch, response.payload)
            except ProtocolFailure:
                result = None
            if result is None:
                outcomes = {cui: CuiOutcome(
                    "INCOMPLET", error_code="STRUCTURA_RASPUNS",
                    error_message="Raspunsul ANAF nu contine liste found si notFound valide.",
                ) for cui in batch}
                totals["incomplete"] += len(batch)
                totals["anomalies"] += 1
                result_message = "structura raspunsului invalida"
            else:
                outcomes = result.outcomes
                totals["found"] += result.found
                totals["not_found"] += result.not_found
                totals["incomplete"] += result.incomplete
                totals["anomalies"] += result.anomalies
                result_message = (f"gasite={result.found}, notFound={result.not_found}, "
                                  f"incomplete={result.incomplete}, anomalii={result.anomalies}")
            entries = [HistoryEntry(
                cui=cui, rulare_id=run_id, incercat_la=response.attempted_at,
                data_interogarii=args.date, nr_lot=index, nr_incercare=response.attempts,
                rezultat=outcomes[cui].result, http_status=response.http_status,
                cod_eroare=outcomes[cui].error_code,
                mesaj_eroare=outcomes[cui].error_message, values=outcomes[cui].values,
            ) for cui in batch]
            persist_attempt(args.db, entries)
            print(f"Lot {index}/{len(batches)} incercarea {response.attempts}: {result_message}.")
        except RequestFailure as exc:
            totals["failed"] += 1
            print(f"Lot {index}/{len(batches)} esuat: {exc}; datele anterioare au fost pastrate.",
                  file=sys.stderr)
    print("Total: " + ", ".join((
        f"rulare_id={run_id}", f"CUI={len(cuis)}", f"loturi procesate={len(batches)}",
        f"cereri HTTP={client.request_count}", f"gasite={totals['found']}",
        f"notFound={totals['not_found']}", f"incomplete={totals['incomplete']}",
        f"inregistrari eroare={totals['error_records']}",
        f"loturi esuate={totals['failed']}", f"anomalii={totals['anomalies']}",
    )))
    return 1 if totals["failed"] else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init-db":
            initialize_database(args.db)
            print(f"Schema SQLite initializata: {args.db}")
            return 0
        if args.command == "import-cui":
            imported, duplicates, invalid = import_cui(args.db, args.input)
            print(f"Randuri importate={imported}, duplicate={duplicates}, invalide={invalid}.")
            return 1 if invalid else 0
        return _run(args)
    except KeyboardInterrupt:
        print("Oprire solicitata; loturile deja salvate au fost pastrate.", file=sys.stderr)
        return 130
    except (DatabaseError, OSError, sqlite3.Error, ValueError) as exc:
        print(f"Eroare: {exc}", file=sys.stderr)
        return 2
