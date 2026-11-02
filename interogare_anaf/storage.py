"""SQLite operations. The checked-in SQL file is the sole schema authority."""

import csv
from pathlib import Path
import re
import sqlite3
from dataclasses import dataclass

from .normalization import normalize_text

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"
MAX_SQLITE_INTEGER = 2**63 - 1
_ASCII_DIGITS = re.compile(r"[0-9]+\Z")


class DatabaseError(Exception):
    """A missing or unusable application database."""


@dataclass(frozen=True)
class HistoryEntry:
    cui: int
    rulare_id: str
    incercat_la: str
    data_interogarii: str
    nr_lot: int
    nr_incercare: int
    rezultat: str
    http_status: int | None = None
    cod_eroare: str | None = None
    mesaj_eroare: str | None = None
    values: tuple[str | None, ...] | None = None


_HISTORY_RESULTS = {"GASIT", "NEGASIT", "EROARE", "INCOMPLET"}


def initialize_database(path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    finally:
        connection.close()


def connect_existing(path: Path) -> sqlite3.Connection:
    path = Path(path)
    if not path.is_file():
        raise DatabaseError(f"Baza de date nu exista: {path}. Ruleaza mai intai init-db.")
    connection = sqlite3.connect(path, timeout=30)
    connection.isolation_level = None  # fiecare INSERT/UPDATE este atomic
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _parse_cui(raw: object) -> int:
    if not isinstance(raw, str) or not _ASCII_DIGITS.fullmatch(raw):
        raise ValueError("CUI trebuie sa contina numai cifre ASCII")
    value = int(raw)
    if value <= 0 or value > MAX_SQLITE_INTEGER:
        raise ValueError("CUI trebuie sa fie un INTEGER SQLite pozitiv")
    return value


def import_cui(path: Path, csv_path: Path) -> tuple[int, int, int]:
    """Import rows; return valid rows, duplicate rows and invalid rows."""
    connection = connect_existing(path)
    imported = duplicates = invalid = 0
    try:
        with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source, delimiter=";")
            if reader.fieldnames != ["cui", "denumire_initiala"]:
                raise ValueError("Antet CSV invalid; este necesar: cui;denumire_initiala")
            for line_number, row in enumerate(reader, start=2):
                try:
                    if None in row:
                        raise ValueError("prea multe coloane")
                    cui = _parse_cui(row.get("cui"))
                    initial_name = row.get("denumire_initiala")
                    if initial_name is None:
                        raise ValueError("rand CSV incomplet")
                    initial_name = normalize_text(initial_name)
                    exists = connection.execute(
                        "SELECT 1 FROM parteneri WHERE cui = ?", (cui,)
                    ).fetchone() is not None
                    connection.execute(
                        """INSERT INTO parteneri (cui, denumire_initiala) VALUES (?, ?)
                           ON CONFLICT(cui) DO UPDATE SET denumire_initiala =
                           CASE WHEN excluded.denumire_initiala <> ''
                                THEN excluded.denumire_initiala
                                ELSE parteneri.denumire_initiala END""",
                        (cui, initial_name),
                    )
                    imported += 1
                    duplicates += int(exists)
                except (ValueError, TypeError):
                    invalid += 1
                    print(f"Randul {line_number}: invalid; omis.")
    finally:
        connection.close()
    return imported, duplicates, invalid


def load_cuis(path: Path, only_missing: bool = False) -> list[int]:
    connection = connect_existing(path)
    try:
        query = "SELECT cui FROM parteneri"
        if only_missing:
            query += " WHERE denumire_anaf IS NULL"
        query += " ORDER BY cui"
        return [row[0] for row in connection.execute(query)]
    finally:
        connection.close()


def persist_attempt(path: Path, entries: list[HistoryEntry]) -> None:
    """Persist one CUI row per outcome; commit GASIT data and history together."""
    connection = connect_existing(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        for entry in entries:
            if entry.rezultat not in _HISTORY_RESULTS:
                raise ValueError(f"Rezultat de istoric invalid: {entry.rezultat}")
            if entry.rezultat == "GASIT":
                if entry.values is None or len(entry.values) != 9:
                    raise ValueError("Rezultatul GASIT necesita exact noua valori ANAF")
                connection.execute(
                    """UPDATE parteneri SET denumire_anaf=?, nrRegCom=?,
                       sdenumire_Localitate=?, sdenumire_Strada=?, snumar_Strada=?,
                       scod_Localitate=?, sdenumire_Judet=?, sdetalii_Adresa=?, scod_Postal=?
                       WHERE cui=?""",
                    (*entry.values, entry.cui),
                )
            connection.execute(
                """INSERT INTO istoric_verificari
                   (cui,rulare_id,incercat_la,data_interogarii,nr_lot,nr_incercare,
                    rezultat,http_status,cod_eroare,mesaj_eroare)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (entry.cui, entry.rulare_id, entry.incercat_la, entry.data_interogarii,
                 entry.nr_lot, entry.nr_incercare, entry.rezultat, entry.http_status,
                 entry.cod_eroare, entry.mesaj_eroare),
            )
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
