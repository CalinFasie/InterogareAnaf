"""Acces SQLite: init-db, import-cui, citirea CUI-urilor si scrierea resultatelor.

Fiecare conexiune este inchisa explicit; context managerul conexiunii
gestioneaza doar tranzactia, nu si finalizarea handle-ului (AGENTS.md #11).
"""

import csv
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .normalize import normalize

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "db" / "schema.sql"

# Cele 9 coloane ANAF din parteneri, in ordinea din schema.
ANAF_COLUMNS = (
    "denumire_anaf",
    "nrRegCom",
    "sdenumire_Localitate",
    "sdenumire_Strada",
    "snumar_Strada",
    "scod_Localitate",
    "sdenumire_Judet",
    "sdetalii_Adresa",
    "scod_Postal",
)

_UPDATE_SQL = (
    "UPDATE parteneri SET "
    + ", ".join('"' + column + '" = ?' for column in ANAF_COLUMNS)
    + " WHERE cui = ?"
)

_CUI_RE = re.compile(r"^\d+$")


class MissingDbError(Exception):
    """Baza de date nu exista; utilizatorul trebuie sa ruleze init-db."""


class CsvError(Exception):
    """Fisierul CSV de import nu respecta contractul."""


@contextmanager
def open_db(db_path):
    """Deschide SQLite, comite la iesire fara exceptie si inchide explicit."""
    connection = sqlite3.connect(str(db_path), timeout=30)
    try:
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def require_db(db_path):
    if not Path(db_path).is_file():
        raise MissingDbError(
            "Baza " + str(db_path)
            + " nu exista sau nu este un fisier. "
            "Ruleaza intai: python -m interogare_anaf init-db --db " + str(db_path)
        )


def now_utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def init_db(db_path):
    """Creeaza directorul parinte si aplica db/schema.sql idempotent."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open_db(path) as database:
        database.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def import_csv(db_path, csv_path):
    """Popularea initiala: citeste CSV (;) si inscrie/actualizeaza parteneri."""
    require_db(db_path)
    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.reader(handle, delimiter=";"))
    except FileNotFoundError:
        raise CsvError("Fisierul CSV nu exista: " + str(csv_path)) from None

    if not rows:
        raise CsvError("Fisierul CSV este gol.")
    header = [cell.strip() for cell in rows[0]]
    if header[:2] != ["cui", "denumire_initiala"]:
        raise CsvError("Antetul CSV trebuie sa fie exact: cui;denumire_initiala")

    imported = duplicates = invalid = 0
    with open_db(db_path) as database:
        for raw_row in rows[1:]:
            if not raw_row or all(not str(cell).strip() for cell in raw_row):
                continue
            cui_raw = str(raw_row[0]).strip() if raw_row else ""
            name_raw = str(raw_row[1]).strip() if len(raw_row) > 1 else ""
            name = normalize(name_raw) or ""
            if not _CUI_RE.match(cui_raw) or int(cui_raw) <= 0:
                invalid += 1
                continue
            cui = int(cui_raw)
            existing = database.execute(
                "SELECT denumire_initiala FROM parteneri WHERE cui = ?", (cui,)
            ).fetchone()
            if existing is None:
                database.execute(
                    "INSERT INTO parteneri (cui, denumire_initiala) VALUES (?, ?)",
                    (cui, name),
                )
                imported += 1
            else:
                duplicates += 1
                if name and name != (existing[0] or ""):
                    database.execute(
                        "UPDATE parteneri SET denumire_initiala = ? WHERE cui = ?",
                        (name, cui),
                    )
    print(
        "Import finalizat: "
        + str(imported) + " CUI importate, "
        + str(duplicates) + " duplicate, "
        + str(invalid) + " randuri invalide (sarite)."
    )


def load_cuis(db_path, only_missing):
    require_db(db_path)
    sql = "SELECT cui FROM parteneri"
    if only_missing:
        sql += " WHERE denumire_anaf IS NULL"
    sql += " ORDER BY cui"
    with open_db(db_path) as database:
        return [row[0] for row in database.execute(sql)]


def _insert_history(database, record):
    database.execute(
        """INSERT INTO istoric_verificari
           (cui, rulare_id, incercat_la, data_interogarii, nr_lot, nr_incercare,
            rezultat, http_status, cod_eroare, mesaj_eroare)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        record,
    )


def _history_record(
    cui, rulare_id, stamp, date, lot_no, attempt_no, rezultat, http_status,
    cod=None, message=None,
):
    return (
        cui, rulare_id, stamp, date, lot_no, attempt_no, rezultat,
        http_status, cod, message,
    )


def write_error_rows(
    db_path, cuits, rulare_id, date, lot_no, attempt_no, http_status, cod, message
):
    """Un rand EROARE per CUI din lot, pentru fiecare incercare efectiva."""
    stamp = now_utc()
    with open_db(db_path) as database:
        for cui in cuits:
            _insert_history(
                database,
                _history_record(
                    cui, rulare_id, stamp, date, lot_no, attempt_no,
                    "EROARE", http_status, cod, message,
                ),
            )


def write_resolution(
    db_path,
    found,
    notfound_cuis,
    incomplete_cuis,
    rulare_id,
    date,
    lot_no,
    attempt_no,
    http_status,
):
    """Actualizarea ANAF si istoricul GASIT/NEGASIT/INCOMPLET in aceeasi tranzactie.

    ``found`` mapuieste cui -> dict {coloana: valoare sau None} pentru cele
    9 campuri; CUI-urile notFound/incomplete primesc doar istoric, fara
    modificarea coloanelor ANAF.
    """
    stamp = now_utc()
    with open_db(db_path) as database:
        for cui, values in found.items():
            parameters = [values[column] for column in ANAF_COLUMNS]
            parameters.append(cui)
            database.execute(_UPDATE_SQL, parameters)
            _insert_history(
                database,
                _history_record(
                    cui, rulare_id, stamp, date, lot_no, attempt_no,
                    "GASIT", http_status,
                ),
            )
        for cui in notfound_cuis:
            _insert_history(
                database,
                _history_record(
                    cui, rulare_id, stamp, date, lot_no, attempt_no,
                    "NEGASIT", http_status,
                ),
            )
        for cui in incomplete_cuis:
            _insert_history(
                database,
                _history_record(
                    cui, rulare_id, stamp, date, lot_no, attempt_no,
                    "INCOMPLET", http_status,
                ),
            )
