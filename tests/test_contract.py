"""Common offline contract tests; all subprocess networking is loopback-only."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "db" / "schema.sql"
FIXTURE = json.loads((ROOT / "fixtures" / "anaf_sintetic.json").read_text(encoding="utf-8"))
GUARD = ROOT / "tests" / "network_guard"
EXPECTED_PARTNER_COLUMNS = (
    "cui", "denumire_initiala", "denumire_anaf", "nrRegCom",
    "sdenumire_Localitate", "sdenumire_Strada", "snumar_Strada",
    "scod_Localitate", "sdenumire_Judet", "sdetalii_Adresa", "scod_Postal",
)
EXPECTED_HISTORY_COLUMNS = (
    "id", "cui", "rulare_id", "incercat_la", "data_interogarii", "nr_lot",
    "nr_incercare", "rezultat", "http_status", "cod_eroare", "mesaj_eroare",
)


@contextmanager
def open_sqlite(path):
    """Close SQLite file handles explicitly; Connection.__exit__ only ends a transaction."""
    connection = sqlite3.connect(path, timeout=30)
    try:
        yield connection
    finally:
        connection.close()


class FakeAnafHandler(BaseHTTPRequestHandler):
    calls = []
    call_starts = []
    responses = []
    lock = threading.Lock()

    def do_POST(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            request_body = json.loads(self.rfile.read(size).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self.send_error(400, "bad JSON")
            return
        if self.path != "/fake/tva":
            self.send_error(404)
            return
        with self.lock:
            self.calls.append(request_body)
            self.call_starts.append(time.monotonic())
            if self.responses:
                status, body, headers = self.responses.pop(0)
            else:
                status, body, headers = 200, None, {}
        if body is None and status == 200:
            body = json.dumps(FIXTURE, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for name, value in headers.items():
            self.send_header(name, value)
        if body is not None:
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body is not None:
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def log_message(self, *_args):
        pass


class TestBaselineSchema(unittest.TestCase):
    def test_exact_two_tables_columns_constraints_and_indexes(self):
        connection = sqlite3.connect(":memory:")
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(SCHEMA.read_text(encoding="utf-8"))
            tables = [row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )]
            self.assertEqual(tables, ["istoric_verificari", "parteneri"])
            partner_columns = connection.execute("PRAGMA table_info(parteneri)").fetchall()
            self.assertEqual(tuple(row[1] for row in partner_columns), EXPECTED_PARTNER_COLUMNS)
            self.assertEqual(partner_columns[0][2].upper(), "INTEGER")
            self.assertEqual(partner_columns[0][5], 1)
            history_columns = connection.execute("PRAGMA table_info(istoric_verificari)").fetchall()
            self.assertEqual(tuple(row[1] for row in history_columns), EXPECTED_HISTORY_COLUMNS)
            self.assertEqual(
                connection.execute("PRAGMA foreign_key_list(istoric_verificari)").fetchone()[2],
                "parteneri",
            )
            indexes = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='istoric_verificari'"
            )}
            self.assertTrue({
                "idx_istoric_verificari_cui_timp", "idx_istoric_verificari_rulare",
                "idx_istoric_verificari_timp",
            }.issubset(indexes))
            connection.execute(
                "INSERT INTO parteneri(cui, denumire_initiala) VALUES (?, ?)", (1234567, "TEST")
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO parteneri(cui) VALUES (0)")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """INSERT INTO istoric_verificari
                       (cui,rulare_id,incercat_la,data_interogarii,nr_lot,nr_incercare,rezultat)
                       VALUES (1234567,'run','2026-11-02T10:00:00Z','2026-11-02',1,1,'UNKNOWN')"""
                )
        finally:
            connection.close()


class TestCliOfflineContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeAnafHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/fake/tva"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dbpath = Path(self.tmp.name) / "private" / "parteneri.sqlite3"
        self.csvpath = ROOT / "fixtures" / "parteneri_sintetici.csv"
        with FakeAnafHandler.lock:
            FakeAnafHandler.calls.clear()
            FakeAnafHandler.call_starts.clear()
            FakeAnafHandler.responses.clear()

    def cli(self, *args, expected_returncode=0):
        environment = os.environ.copy()
        existing = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = os.pathsep.join(filter(None, [str(GUARD), str(ROOT), existing]))
        process = subprocess.run(
            [sys.executable, "-m", "interogare_anaf", *map(str, args)],
            cwd=ROOT, env=environment, capture_output=True, text=True, timeout=100,
        )
        self.assertEqual(
            process.returncode, expected_returncode,
            f"CLI {args!r} failed (exit {process.returncode}):\n"
            f"stdout={process.stdout}\nstderr={process.stderr}",
        )
        return process

    def init_and_import(self):
        self.cli("init-db", "--db", self.dbpath)
        self.cli("import-cui", "--db", self.dbpath, "--input", self.csvpath)

    def run_cli(self, *args, expected_returncode=0):
        return self.cli("run", "--db", self.dbpath, "--date", "2026-11-02",
                        "--api-url", self.url, *args, expected_returncode=expected_returncode)

    def test_cli_results_history_only_missing_and_init_is_idempotent(self):
        self.init_and_import()
        with open_sqlite(self.dbpath) as db:
            count = db.execute("SELECT COUNT(*) FROM parteneri").fetchone()[0]
            self.assertEqual(count, 2)
            name = db.execute(
                "SELECT denumire_initiala FROM parteneri WHERE cui=1234567"
            ).fetchone()[0]
            self.assertEqual(name, "Denumire initiala SI TEST SRL")

        self.run_cli()
        with FakeAnafHandler.lock:
            calls = list(FakeAnafHandler.calls)
        self.assertEqual(len(calls), 1)
        self.assertEqual(sorted(x["cui"] for x in calls[0]), [1234567, 7654321])
        self.assertTrue(all(isinstance(x["cui"], int) and x["data"] == "2026-11-02" for x in calls[0]))
        self.assertLessEqual(len(calls[0]), 100)

        with open_sqlite(self.dbpath) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM parteneri WHERE cui=1234567").fetchone()
            self.assertEqual(tuple(row.keys()), EXPECTED_PARTNER_COLUMNS)
            self.assertEqual(row["denumire_initiala"], "Denumire initiala SI TEST SRL")
            self.assertEqual(row["denumire_anaf"], "SOCIETATE TEST SI INCERCARI SRL")
            self.assertEqual(row["nrRegCom"], "J00/123/2020")
            self.assertEqual(row["sdenumire_Localitate"], "Mun. Brasov")
            self.assertEqual(row["sdenumire_Strada"], "Str. Scolii")
            self.assertEqual(row["snumar_Strada"], "12A")
            self.assertEqual(row["scod_Localitate"], "000316")
            self.assertEqual(row["sdenumire_Judet"], "BRASOV")
            self.assertEqual(row["sdetalii_Adresa"], "Cladirea A, etaj T")
            self.assertEqual(row["scod_Postal"], "001234")
            absent = db.execute(
                "SELECT denumire_anaf FROM parteneri WHERE cui=7654321"
            ).fetchone()[0]
            self.assertIsNone(absent)
            history = db.execute(
                "SELECT cui, rezultat, nr_lot, nr_incercare, rulare_id FROM istoric_verificari ORDER BY cui"
            ).fetchall()
            self.assertEqual([(r[0], r[1], r[2], r[3]) for r in history], [
                (1234567, "GASIT", 1, 1), (7654321, "NEGASIT", 1, 1),
            ])
            first_run_id = history[0][4]
            self.assertEqual(history[1][4], first_run_id)

        self.run_cli("--only-missing")
        with FakeAnafHandler.lock:
            calls = list(FakeAnafHandler.calls)
        self.assertEqual(len(calls), 2)
        self.assertEqual([x["cui"] for x in calls[-1]], [7654321])
        with open_sqlite(self.dbpath) as db:
            history = db.execute(
                "SELECT cui,resultado,rulare_id FROM istoric_verificari ORDER BY id"
            ).fetchall()
            self.assertEqual(len(history), 3)
            self.assertEqual(history[-1][0:2], (7654321, "NEGASIT"))
            self.assertNotEqual(history[-1][2], first_run_id)
        self.cli("init-db", "--db", self.dbpath)
        with open_sqlite(self.dbpath) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM parteneri").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM istoric_verificari").fetchone()[0], 3)

    def test_retry_attempts_all_outcomes_append_only_and_errors_preserve_data(self):
        self.init_and_import()
        with open_sqlite(self.dbpath) as db:
            db.execute("INSERT INTO parteneri(cui, denumire_anaf) VALUES (3450001, 'Pastreaza-ma')")
            db.execute("UPDATE parteneri SET denumire_anaf='Valoare veche' WHERE cui=7654321")
        with FakeAnafHandler.lock:
            FakeAnafHandler.responses.extend([
                (429, b"", {"Retry-After": "0"}),
                (200, None, {}),
            ])
        self.run_cli()
        with FakeAnafHandler.lock:
            first_run_calls = len(FakeAnafHandler.calls)
            first_run_starts = list(FakeAnafHandler.call_starts)
        self.assertEqual(first_run_calls, 2)
        self.assertGreaterEqual(first_run_starts[1] - first_run_starts[0], 1.0)

        with open_sqlite(self.dbpath) as db:
            rows = db.execute(
                """SELECT cui,nr_incercare,rezultat,http_status FROM istoric_verificari
                   ORDER BY nr_incercare,cui"""
            ).fetchall()
            self.assertEqual(len(rows), 6)
            self.assertEqual([(r[0], r[1], r[2], r[3]) for r in rows[:3]], [
                (1234567, 1, "EROARE", 429), (3450001, 1, "EROARE", 429),
                (7654321, 1, "EROARE", 429),
            ])
            self.assertEqual({r[2] for r in rows[3:]}, {"GASIT", "NEGASIT", "INCOMPLET"})
            self.assertEqual(db.execute(
                "SELECT denumire_anaf FROM parteneri WHERE cui=7654321"
            ).fetchone()[0], "Valoare veche")
            first_run_id = rows[0][4] if len(rows[0]) > 4 else db.execute(
                "SELECT rulare_id FROM istoric_verificari ORDER BY id LIMIT 1"
            ).fetchone()[0]

        with FakeAnafHandler.lock:
            FakeAnafHandler.responses.extend([(503, b"", {}) for _ in range(3)])
        self.run_cli(expected_returncode=1)
        with FakeAnafHandler.lock:
            later_starts = list(FakeAnafHandler.call_starts[first_run_calls:])
        self.assertEqual(len(later_starts), 3)
        self.assertGreaterEqual(later_starts[1] - later_starts[0], 1.0)
        self.assertGreaterEqual(later_starts[2] - later_starts[1], 1.0)
        with open_sqlite(self.dbpath) as db:
            rows = db.execute(
                """SELECT cui,nr_incercare,rezultat,http_status,rulare_id FROM istoric_verificari
                   ORDER BY id"""
            ).fetchall()
            self.assertEqual(len(rows), 15)
            errors = rows[6:]
            self.assertEqual(len(errors), 9)
            self.assertTrue(all(r[2] == "EROARE" and r[3] == 503 for r in errors))
            self.assertEqual({r[1] for r in errors}, {1, 2, 3})
            self.assertNotEqual(errors[0][4], first_run_id)
            self.assertEqual(db.execute(
                "SELECT denumire_anaf FROM parteneri WHERE cui=1234567"
            ).fetchone()[0], "SOCIETATE TEST SI INCERCARI SRL")
            self.assertEqual(db.execute(
                "SELECT denumire_anaf FROM parteneri WHERE cui=7654321"
            ).fetchone()[0], "Valoare veche")

    def test_invalid_json_is_logged_and_does_not_overwrite_anaf(self):
        self.init_and_import()
        with open_sqlite(self.dbpath) as db:
            db.execute("UPDATE parteneri SET denumire_anaf='Valoare valida' WHERE cui=1234567")
        with FakeAnafHandler.lock:
            FakeAnafHandler.responses.append((200, b"not-json", {}))
        self.run_cli(expected_returncode=1)
        with open_sqlite(self.dbpath) as db:
            rows = db.execute(
                "SELECT rezultat,http_status,cod_eroare FROM istoric_verificari ORDER BY cui"
            ).fetchall()
            self.assertEqual(rows, [
                ("EROARE", 200, "JSON_INVALID"), ("EROARE", 200, "JSON_INVALID"),
            ])
            self.assertEqual(db.execute(
                "SELECT denumire_anaf FROM parteneri WHERE cui=1234567"
            ).fetchone()[0], "Valoare valida")

    def test_four_thousand_cuis_make_forty_requests_of_at_most_one_hundred(self):
        self.cli("init-db", "--db", self.dbpath)
        with open_sqlite(self.dbpath) as db:
            db.executemany("INSERT INTO parteneri(cui) VALUES (?)", ((cui,) for cui in range(1, 4001)))
        self.run_cli()
        with FakeAnafHandler.lock:
            calls = list(FakeAnafHandler.calls)
            starts = list(FakeAnafHandler.call_starts)
        self.assertEqual(len(calls), 40)
        self.assertTrue(all(len(batch) <= 100 for batch in calls))
        self.assertEqual([item["cui"] for batch in calls for item in batch], list(range(1, 4001)))
        self.assertTrue(all(later - earlier >= 1.0 for earlier, later in zip(starts, starts[1:])))
        with open_sqlite(self.dbpath) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM istoric_verificari").fetchone()[0], 4000)
            self.assertEqual(db.execute(
                "SELECT COUNT(DISTINCT nr_lot) FROM istoric_verificari"
            ).fetchone()[0], 40)


if __name__ == "__main__":
    unittest.main()
