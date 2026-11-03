"""Final robustness checks using synthetic data and loopback only."""

from argparse import Namespace
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from interogare_anaf.client import (
    AnafClient, BatchResponse, ProtocolFailure, RequestPacer, _retry_after_seconds,
    apply_payload,
)
from interogare_anaf.cli import _run
from interogare_anaf.storage import (
    HistoryEntry, import_cui, initialize_database, persist_attempt,
)


class FakeTime:
    def __init__(self):
        self.value = 0.0

    def clock(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class FinalRobustnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "private" / "partners.sqlite3"
        initialize_database(self.db)

    def test_client_rejects_invalid_cuis_dates_and_timeouts_before_network(self):
        class NeverOpen:
            def __call__(self, *_args, **_kwargs):
                raise AssertionError("network call was not expected")

        for timeout in (0, -1, float("nan"), float("inf"), True):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                AnafClient(timeout=timeout, opener=NeverOpen())

        client = AnafClient(opener=NeverOpen())
        for interval in (0.99, float("nan"), float("inf"), True):
            with self.subTest(interval=interval), self.assertRaises(ValueError):
                RequestPacer(interval=interval)
        for cuis in ([0], [-1], [True], [2**63], ["123"]):
            with self.subTest(cuis=cuis), self.assertRaises(ValueError):
                client.fetch(cuis, "2026-11-03")
        for invalid_date in ("2026-2-03", "2026-02-30", "03-11-2026", "2026-11-03 "):
            with self.subTest(date=invalid_date), self.assertRaises(ValueError):
                client.fetch([1234567], invalid_date)

    def test_retry_after_parses_numeric_and_http_date_and_ignores_nonfinite(self):
        self.assertEqual(_retry_after_seconds("2.5"), 2.5)
        self.assertEqual(_retry_after_seconds("-1"), 0.0)
        self.assertIsNone(_retry_after_seconds("NaN"))
        self.assertIsNone(_retry_after_seconds("Infinity"))
        future = datetime.now(timezone.utc) + timedelta(seconds=90)
        seconds = _retry_after_seconds(format_datetime(future, usegmt=True))
        self.assertIsNotNone(seconds)
        self.assertGreaterEqual(seconds, 88)
        self.assertLessEqual(seconds, 90)

    def test_response_validation_marks_affected_cuis_incomplete_without_overwrite(self):
        with sqlite3.connect(self.db) as db:
            db.executemany(
                "INSERT INTO parteneri(cui, denumire_initiala, denumire_anaf) VALUES (?,?,?)",
                [(101, "Initiala 101", "Vechi 101"), (102, "Initiala 102", "Vechi 102"),
                 (103, "Initiala 103", "Vechi 103"), (104, "Initiala 104", "Vechi 104")],
            )
        db.close()
        payload = {
            "found": [
                {"date_generale": {"cui": 101, "denumire": "Primul"},
                 "adresa_sediu_social": {}},
                {"date_generale": {"cui": 101, "denumire": "Duplicat"},
                 "adresa_sediu_social": {}},
                {"date_generale": {"cui": 102, "denumire": "Contradictoriu"},
                 "adresa_sediu_social": {}},
                {"date_generale": {"cui": 103, "denumire": 13},
                 "adresa_sediu_social": {}},
                {"date_generale": {"cui": 999, "denumire": "Strain"},
                 "adresa_sediu_social": {}},
                {"date_generale": {"cui": 104, "denumire": "Structura"},
                 "adresa_sediu_social": []},
            ],
            "notFound": [102, 104],
        }
        result = apply_payload([101, 102, 103, 104], payload)
        self.assertEqual(result.incomplete, 4)
        self.assertEqual(result.found + result.not_found, 0)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute(
                "SELECT cui,denumire_anaf FROM parteneri ORDER BY cui"
            ).fetchall(), [(101, "Vechi 101"), (102, "Vechi 102"),
                           (103, "Vechi 103"), (104, "Vechi 104")])
        db.close()

    def test_required_lists_and_json_field_types_are_strict(self):
        for payload in ({}, {"found": {}, "notFound": []},
                        {"found": [], "notFound": None}):
            with self.subTest(payload=payload), self.assertRaises(ProtocolFailure):
                apply_payload([1], payload)
        for invalid in (9, False, [], {}):
            result = apply_payload([1], {
                "found": [{"date_generale": {"cui": 1, "nrRegCom": invalid},
                           "adresa_sediu_social": {}}],
                "notFound": [],
            })
            self.assertEqual(result.outcomes[1].result, "INCOMPLET")
            self.assertEqual(result.outcomes[1].values, None)
        valid = apply_payload([1], {
            "found": [{"date_generale": {"cui": 1}, "adresa_sediu_social": {}}],
            "notFound": [],
        })
        self.assertEqual(valid.outcomes[1].result, "GASIT")
        self.assertEqual(valid.outcomes[1].values, (None,) * 9)

        class JsonArrayResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b"[]"

        response = AnafClient(
            "http://127.0.0.1/fake", opener=lambda *_args, **_kwargs: JsonArrayResponse(),
        ).fetch([1], "2026-11-03")
        with self.assertRaises(ProtocolFailure):
            apply_payload([1], response.payload)

    def test_import_rejects_out_of_range_values_without_poisoning_valid_rows(self):
        source = self.root / "synthetic.csv"
        source.write_text(
            "cui;denumire_initiala\n0;zero\n-1;negativ\nRO12;prefix\n"
            "9223372036854775808;prea mare\n9223372036854775807;valid\n",
            encoding="utf-8-sig",
        )
        self.assertEqual(import_cui(self.db, source), (1, 0, 4))
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute(
                "SELECT cui,denumire_initiala FROM parteneri"
            ).fetchall(), [(2**63 - 1, "valid")])
        db.close()

    def test_history_constraints_foreign_keys_and_atomic_rollback(self):
        with self.assertRaises(sqlite3.IntegrityError):
            persist_attempt(self.db, [HistoryEntry(
                cui=77, rulare_id="orphan", incercat_la="2026-11-03T00:00:00Z",
                data_interogarii="2026-11-03", nr_lot=1, nr_incercare=1,
                rezultat="NEGASIT",
            )])
        with sqlite3.connect(self.db) as db:
            db.execute("INSERT INTO parteneri(cui,denumire_anaf) VALUES (1,'Old')")
            db.execute("""CREATE TRIGGER deny_history BEFORE INSERT ON istoric_verificari
                       BEGIN SELECT RAISE(ABORT,'synthetic rejection'); END""")
        db.close()
        with self.assertRaises(sqlite3.IntegrityError):
            persist_attempt(self.db, [HistoryEntry(
                cui=1, rulare_id="atomic", incercat_la="2026-11-03T00:00:00Z",
                data_interogarii="2026-11-03", nr_lot=1, nr_incercare=1,
                rezultat="GASIT", values=("New",) + (None,) * 8,
            )])
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute(
                "SELECT denumire_anaf FROM parteneri WHERE cui=1"
            ).fetchone()[0], "Old")
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM istoric_verificari"
            ).fetchone()[0], 0)
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        db.close()

    def test_resume_after_interrupt_keeps_committed_batches_and_only_missing_scope(self):
        with sqlite3.connect(self.db) as db:
            db.executemany("INSERT INTO parteneri(cui) VALUES (?)", ((i,) for i in range(1, 102)))
        db.close()

        class InterruptingClient:
            calls = 0

            def __init__(self, **_kwargs):
                self.request_count = 0

            def fetch(self, batch, _date, on_error_attempt=None):
                self.calls += 1
                self.request_count += 1
                if self.calls == 2:
                    raise KeyboardInterrupt
                self.assert_batch = list(batch)
                found = [{"date_generale": {"cui": cui, "denumire": "SYNTHETIC"},
                          "adresa_sediu_social": {}} for cui in batch]
                return BatchResponse({"found": found, "notFound": []}, 1, 200,
                                     "2026-11-03T00:00:00.000000Z")

        args = Namespace(db=self.db, only_missing=False, api_url="http://127.0.0.1/fake",
                         timeout=2.0, date="2026-11-03")
        with patch("interogare_anaf.cli.AnafClient", InterruptingClient):
            with self.assertRaises(KeyboardInterrupt):
                _run(args)

        class ResumeClient:
            batches = []

            def __init__(self, **_kwargs):
                self.request_count = 0

            def fetch(self, batch, _date, on_error_attempt=None):
                self.batches.append(list(batch))
                self.request_count += 1
                return BatchResponse({"found": [], "notFound": batch}, 1, 200,
                                     "2026-11-03T00:00:01.000000Z")

        resume = ResumeClient()
        args.only_missing = True
        with patch("interogare_anaf.cli.AnafClient", return_value=resume):
            self.assertEqual(_run(args), 0)
        self.assertEqual(ResumeClient.batches, [[101]])
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM istoric_verificari"
            ).fetchone()[0], 101)
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        db.close()

    def test_4000_cuis_use_exactly_forty_sequential_batches(self):
        with sqlite3.connect(self.db) as db:
            db.executemany("INSERT INTO parteneri(cui) VALUES (?)", ((i,) for i in range(1, 4001)))
        db.close()

        class CaptureClient:
            sizes = []
            all_cuis = []

            def __init__(self, **_kwargs):
                self.request_count = 0

            def fetch(self, batch, _date, on_error_attempt=None):
                self.sizes.append(len(batch))
                self.all_cuis.extend(batch)
                self.request_count += 1
                return BatchResponse({"found": [], "notFound": batch}, 1, 200,
                                     "2026-11-03T00:00:00.000000Z")

        args = Namespace(db=self.db, only_missing=False, api_url="http://127.0.0.1/fake",
                         timeout=2.0, date="2026-11-03")
        client = CaptureClient()
        with patch("interogare_anaf.cli.AnafClient", return_value=client):
            self.assertEqual(_run(args), 0)
        self.assertEqual(CaptureClient.sizes, [100] * 40)
        self.assertEqual(CaptureClient.all_cuis, list(range(1, 4001)))
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM istoric_verificari"
            ).fetchone()[0], 4000)
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        db.close()


if __name__ == "__main__":
    unittest.main()
