"""Orchestrarea executiei `run`: loturi, pacing, retry, istoric, raportare."""

import time
import uuid

from . import anaf
from .database import load_cuis, write_error_rows, write_resolution


def _pacing_wait(last_start):
    if not last_start:
        return 0.0
    elapsed = time.monotonic() - last_start
    wait = anaf.REQUEST_INTERVAL + anaf.PACE_MARGIN - elapsed
    return wait if wait > 0.0 else 0.0


def execute_run(db_path, date, api_url, timeout, only_missing):
    """Ruleaza interogarea ANAF pentru toate CUI-urile din baza.

    Intoarce codul de iesire: 0 daca toate loturile au fost rezolvate
    (GASIT/NEGASIT/INCOMPLET), 1 daca exista loturi neizbutite (EROARE).
    """
    cuits = load_cuis(db_path, only_missing)
    if not cuits:
        print("Niciun CUI de procesat in baza.")
        return 0

    rulare_id = str(uuid.uuid4())
    batches = anaf.split_batches(cuits)
    found_total = notfound_total = incomplete_total = error_total = 0
    failed_lots = 0
    last_start = 0.0

    print(
        "Rulez interogarea: " + str(len(cuits)) + " CUI in "
        + str(len(batches)) + " loturi (rulare " + rulare_id + ")."
    )

    for lot_no, batch in enumerate(batches, start=1):
        resolved = False
        for attempt_no in range(1, anaf.MAX_ATTEMPTS + 1):
            time.sleep(_pacing_wait(last_start))
            last_start = time.monotonic()
            try:
                status, body = anaf.post_batch(api_url, batch, date, timeout)
            except anaf.AnafError as error:
                write_error_rows(
                    db_path, batch, rulare_id, date, lot_no, attempt_no,
                    error.http_status, error.cod, error.message,
                )
                error_total += len(batch)
                if error.transient:
                    detail = "HTTP " + str(error.http_status) if error.http_status else error.cod
                    print(
                        "Lot " + str(lot_no) + ": incercarea " + str(attempt_no)
                        + " a esuat (" + str(detail) + "); reintentare."
                    )
                    if error.retry_after:
                        time.sleep(error.retry_after)
                    continue
                print("Lot " + str(lot_no) + ": eroare permanenta (" + str(error.cod) + ").")
                break

            try:
                found, notfound, incomplete, anomalies = anaf.parse_response(body, batch)
            except anaf.InvalidJson:
                write_error_rows(
                    db_path, batch, rulare_id, date, lot_no, attempt_no,
                    status, "JSON_INVALID", "Raspuns JSON invalid",
                )
                error_total += len(batch)
                print("Lot " + str(lot_no) + ": raspuns JSON invalid.")
                break

            for message in anomalies:
                print("Anomalie lot " + str(lot_no) + ": " + message)
            write_resolution(
                db_path, found, notfound, incomplete,
                rulare_id, date, lot_no, attempt_no, status,
            )
            found_total += len(found)
            notfound_total += len(notfound)
            incomplete_total += len(incomplete)
            resolved = True
            break

        if not resolved:
            failed_lots += 1

    print(
        "Raport: CUI citite: " + str(len(cuits))
        + "; loturi: " + str(len(batches))
        + " (nesoluite: " + str(failed_lots) + ")"
        + "; GASIT: " + str(found_total)
        + "; NEGASIT: " + str(notfound_total)
        + "; INCOMPLET: " + str(incomplete_total)
        + "; EROARE: " + str(error_total) + "."
    )
    return 1 if failed_lots else 0
