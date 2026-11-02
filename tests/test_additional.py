"""Additional offline edge-case tests; all HTTP traffic stays on loopback."""

from argparse import Namespace
from collections import Counter
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from interogare_anaf.client import (
    AnafClient, BatchResponse, RequestFailure, RequestPacer, apply_payload,
)
from interogare_anaf.cli import _run
from interogare_anaf.storage import import_cui, initialize_database

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "fixtures" / "anaf_sintetic.json").read_text(encoding="utf-8"))


class FakeTime:
    def __init__(self):
        self.now = 0.0

    def clock(self):
        return self.now

    def sleep(self, delay):
        self.now += delay


class RetryHandler(BaseHTTPRequestHandler):
    attempts = 0
    request_times = []
    lock = threading.Lock()

    def do_POST(self):
        size = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(size).decode("utf-8"))
        with self.lock:
            type(self).attempts += 1
            attempt = type(self).attempts
            type(self).request_times.append((attempt, body))
        if attempt == 1:
            self.send_response(429)
            self.send_header("Retry-After", "0")
            self.end_headers()
            return
        if attempt == 2:
            self.send_response(503)
            self.end_headers()
            return
        response = json.dumps(FIXTURE, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, *_args):
        pass


class AdditionalOfflineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "nested" / "parteneri.sqlite3"
        initialize_database(self.db)

    def test_import_skips_invalid_and_preserves_anaf_and_nonempty_initial_name(self):
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                "INSERT INTO parteneri(cui, denumire_initiala, denumire_anaf) VALUES (?, ?, ?)",
                (1234567, "Initiala", "Nume ANAF deja existent"),
            )
        connection.close()
        csv_path = self.root / "import.csv"
        csv_path.write_text(
            "cui;denumire_initiala\n"
            "1234567;\n"
            "1234567;Noua denumire ȘI firmă\n"
            "RO7654321;Invalid\n"
            "-12;Invalid\n"
            "1.5;Invalid\n"
            ";Lipsa\n",
            encoding="utf-8-sig",
        )
        imported, duplicates, invalid = import_cui(self.db, csv_path)
        self.assertEqual((imported, duplicates, invalid), (2, 2, 4))
        with sqlite3.connect(self.db) as connection:
            row = connection.execute(
                "SELECT denumire_initiala, denumire_anaf FROM parteneri WHERE cui=1234567"
            ).fetchone()
        connection.close()
        self.assertEqual(row, ("Noua denumire SI firma", "Nume ANAF deja existent"))

    def test_ambiguous_foreign_and_invalid_found_entries_do_not_overwrite(self):
        initialize_database(self.db)
        with sqlite3.connect(self.db) as connection:
            connection.executemany(
                "INSERT INTO parteneri(cui, denumire_initiala, denumire_anaf) VALUES (?, ?, ?)",
                [(1234567, "Original", "Keep one"), (7654321, "Other", "Keep two")],
            )
        connection.close()
        payload = {
            "found": [
                {"date_generale": {"cui": 1234567, "denumire": "First"},
                 "adresa_sediu_social": {}},
                {"date_generale": {"cui": 1234567, "denumire": "Duplicate"},
                 "adresa_sediu_social": {}},
                {"date_generale": {"cui": 7654321, "denumire": "Bad type"},
                 "adresa_sediu_social": {"scod_Postal": 123}},
                {"date_generale": {"cui": 9999999, "denumire": "Foreign"},
                 "adresa_sediu_social": {}},
            ],
            "notFound": [],
        }
        result = apply_payload(self.db, [1234567, 7654321], payload)
        self.assertEqual((result.found, result.not_found, result.incomplete), (0, 0, 2))
        self.assertGreaterEqual(result.anomalies, 3)
        with sqlite3.connect(self.db) as connection:
            rows = connection.execute(
                "SELECT cui, denumire_anaf FROM parteneri ORDER BY cui"
            ).fetchall()
        connection.close()
        self.assertEqual(rows, [(1234567, "Keep one"), (7654321, "Keep two")])

    def test_missing_selected_keys_clear_only_anaf_fields(self):
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                """INSERT INTO parteneri(cui, denumire_initiala, denumire_anaf, nrRegCom,
                   sdenumire_Localitate) VALUES (1234567, 'Initial', 'Old name', 'J1', 'Old town')"""
            )
        connection.close()
        payload = {
            "found": [{
                "date_generale": {"cui": 1234567, "denumire": "Noua Și Firmă", "nrRegCom": ""},
                "adresa_sediu_social": {"scod_Localitate": "000001"},
                "adresa": {"sdenumire_Strada": "ignored"},
            }],
            "notFound": [],
        }
        result = apply_payload(self.db, [1234567], payload)
        self.assertEqual(result.found, 1)
        with sqlite3.connect(self.db) as connection:
            row = connection.execute(
                "SELECT denumire_initiala, denumire_anaf, nrRegCom, sdenumire_Localitate, "
                "sdenumire_Strada, scod_Localitate FROM parteneri WHERE cui=1234567"
            ).fetchone()
        connection.close()
        self.assertEqual(row, ("Initial", "Noua Si Firma", None, None, None, "000001"))

    def test_retry_after_and_server_errors_obey_pacing(self):
        RetryHandler.attempts = 0
        RetryHandler.request_times = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), RetryHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.addCleanup(thread.join, 5)

        fake_time = FakeTime()
        pacer = RequestPacer(clock=fake_time.clock, sleeper=fake_time.sleep)
        client = AnafClient(
            f"http://127.0.0.1:{server.server_port}/fake/tva", pacer=pacer
        )
        response = client.fetch([1234567], "2026-10-28")
        self.assertEqual(response.attempts, 3)
        self.assertEqual(client.request_count, 3)
        self.assertEqual([attempt for attempt, _ in RetryHandler.request_times], [1, 2, 3])
        self.assertTrue(all(len(body) <= 100 for _, body in RetryHandler.request_times))
        self.assertEqual(fake_time.now, 3.0)
        self.assertEqual(response.payload["found"][0]["date_generale"]["cui"], 1234567)

    def test_timeout_retries_three_times_but_permanent_http_and_bad_json_do_not(self):
        class TimeoutOpener:
            calls = 0

            def __call__(self, *_args, **_kwargs):
                self.calls += 1
                raise TimeoutError("offline timeout")

        fake_time = FakeTime()
        timeout_opener = TimeoutOpener()
        timeout_client = AnafClient(
            "http://127.0.0.1/fake", opener=timeout_opener,
            pacer=RequestPacer(clock=fake_time.clock, sleeper=fake_time.sleep),
        )
        with self.assertRaisesRegex(RequestFailure, "dupa 3 incercari"):
            timeout_client.fetch([1234567], "2026-10-28")
        self.assertEqual(timeout_opener.calls, 3)
        self.assertEqual(fake_time.now, 3.0)

        class PermanentOpener:
            calls = 0

            def __call__(self, request, **_kwargs):
                self.calls += 1
                raise HTTPError(request.full_url, 400, "bad request", {}, None)

        permanent_opener = PermanentOpener()
        permanent_client = AnafClient("http://127.0.0.1/fake", opener=permanent_opener)
        with self.assertRaisesRegex(RequestFailure, "HTTP 400 permanent"):
            permanent_client.fetch([1234567], "2026-10-28")
        self.assertEqual(permanent_opener.calls, 1)

        class InvalidJsonResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b"not-json"

        class InvalidJsonOpener:
            calls = 0

            def __call__(self, *_args, **_kwargs):
                self.calls += 1
                return InvalidJsonResponse()

        invalid_opener = InvalidJsonOpener()
        invalid_client = AnafClient("http://127.0.0.1/fake", opener=invalid_opener)
        with self.assertRaisesRegex(RequestFailure, "raspuns JSON invalid"):
            invalid_client.fetch([1234567], "2026-10-28")
        self.assertEqual(invalid_opener.calls, 1)

    def test_four_thousand_cuis_are_split_into_forty_sorted_batches(self):
        with sqlite3.connect(self.db) as connection:
            connection.executemany(
                "INSERT INTO parteneri(cui) VALUES (?)",
                ((cui,) for cui in range(1, 4001)),
            )
        connection.close()

        class FakeClient:
            def __init__(self, **_kwargs):
                self.request_count = 0
                self.sizes = []
                self.cuis = []

            def fetch(self, batch, _query_date):
                self.request_count += 1
                self.sizes.append(len(batch))
                self.cuis.extend(batch)
                return BatchResponse({"found": [], "notFound": list(batch)}, 1)

        fake_client = FakeClient()
        args = Namespace(db=self.db, only_missing=False, api_url="http://127.0.0.1/unused",
                         timeout=1.0, date="2026-10-28")
        with patch("interogare_anaf.cli.AnafClient", return_value=fake_client):
            exit_code = _run(args)
        self.assertEqual(exit_code, 0)
        self.assertEqual(fake_client.request_count, 40)
        self.assertEqual(fake_client.sizes, [100] * 40)
        self.assertEqual(fake_client.cuis, list(range(1, 4001)))


if __name__ == "__main__":
    unittest.main()
