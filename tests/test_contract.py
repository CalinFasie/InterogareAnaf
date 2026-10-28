"""Common offline contract tests for both agent implementations.

The CLI is intentionally absent from the baseline and must be built by each agent.
No test makes an ANAF request. Subprocesses have network_guard in PYTHONPATH.
"""
import csv
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "db" / "schema.sql"
FIXTURE = json.loads((ROOT / "fixtures" / "anaf_sintetic.json").read_text(encoding="utf-8"))
GUARD = ROOT / "tests" / "network_guard"
EXPECTED_COLUMNS = (
    "cui", "denumire_initiala", "denumire_anaf", "nrRegCom",
    "sdenumire_Localitate", "sdenumire_Strada", "snumar_Strada",
    "scod_Localitate", "sdenumire_Judet", "sdetalii_Adresa", "scod_Postal",
)


class FakeAnafHandler(BaseHTTPRequestHandler):
    calls = []
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
        response = json.dumps(FIXTURE, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, fmt, *args):
        pass


class TestBaselineSchema(unittest.TestCase):
    def test_exactly_eleven_columns_and_integer_cui(self):
        with sqlite3.connect(":memory:") as db:
            db.executescript(SCHEMA.read_text(encoding="utf-8"))
            tables = [row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )]
            self.assertEqual(tables, ["parteneri"])
            columns = db.execute("PRAGMA table_info(parteneri)").fetchall()
            self.assertEqual(tuple(row[1] for row in columns), EXPECTED_COLUMNS)
            self.assertEqual(columns[0][2].upper(), "INTEGER")
            self.assertEqual(columns[0][5], 1)
            db.execute("INSERT INTO parteneri(cui, denumire_initiala) VALUES (?, ?)", (1234567, "TEST"))
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT INTO parteneri(cui) VALUES (0)")


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

    def cli(self, *args):
        environment = os.environ.copy()
        existing = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = os.pathsep.join(filter(None, [str(GUARD), str(ROOT), existing]))
        process = subprocess.run(
            [sys.executable, "-m", "interogare_anaf", *map(str, args)],
            cwd=ROOT, env=environment, capture_output=True, text=True, timeout=40,
        )
        self.assertEqual(
            process.returncode, 0,
            f"CLI {args!r} failed (exit {process.returncode}):\n"
            f"stdout={process.stdout}\nstderr={process.stderr}",
        )
        return process

    def test_cli_import_found_not_found_normalization_and_only_missing(self):
        self.cli("init-db", "--db", self.dbpath)
        self.cli("import-cui", "--db", self.dbpath, "--input", self.csvpath)
        with sqlite3.connect(self.dbpath) as db:
            count = db.execute("SELECT COUNT(*) FROM parteneri").fetchone()[0]
            self.assertEqual(count, 2)
            name = db.execute("SELECT denumire_initiala FROM parteneri WHERE cui=1234567").fetchone()[0]
            self.assertEqual(name, "Denumire initiala SI TEST SRL")

        self.cli("run", "--db", self.dbpath, "--date", "2026-10-28", "--api-url", self.url)
        with FakeAnafHandler.lock:
            calls = list(FakeAnafHandler.calls)
        self.assertEqual(len(calls), 1)
        self.assertEqual(sorted(x["cui"] for x in calls[0]), [1234567, 7654321])
        self.assertTrue(all(isinstance(x["cui"], int) and x["data"] == "2026-10-28" for x in calls[0]))
        self.assertLessEqual(len(calls[0]), 100)

        with sqlite3.connect(self.dbpath) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM parteneri WHERE cui=1234567").fetchone()
            self.assertEqual(tuple(row.keys()), EXPECTED_COLUMNS)
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
            absent = db.execute("SELECT denumire_anaf FROM parteneri WHERE cui=7654321").fetchone()[0]
            self.assertIsNone(absent)

        self.cli("run", "--db", self.dbpath, "--date", "2026-10-28", "--api-url", self.url, "--only-missing")
        with FakeAnafHandler.lock:
            calls = list(FakeAnafHandler.calls)
        self.assertEqual(len(calls), 2)
        self.assertEqual([x["cui"] for x in calls[-1]], [7654321])


if __name__ == "__main__":
    unittest.main()
