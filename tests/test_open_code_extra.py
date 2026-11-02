"""Teste suplimentare OpenCode Ubuntu (fisier separat, conform promptului comun).

Se adauga pe langa test_contract.py; folosesc doar servere pe 127.0.0.1
si fixture-uri fictive.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "tests" / "network_guard"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from interogare_anaf.normalize import normalize  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    responses = []
    calls = []
    lock = threading.Lock()

    def do_POST(self):
        size = int(self.headers.get("Content-Length", "0"))
        with self.lock:
            Handler.calls.append(
                json.loads(self.rfile.read(size).decode("utf-8"))
            )
            if Handler.responses:
                status, body = Handler.responses.pop(0)
            else:
                status, body = 200, "{}"
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


class OpenCodeExtraBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = "http://127.0.0.1:%d/extra/tva" % cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dbpath = Path(self.tmp.name) / "parteneri.sqlite3"
        with Handler.lock:
            Handler.calls.clear()
            Handler.responses.clear()

    def cli(self, *args, expected_returncode=0):
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join(
            [str(GUARD), str(ROOT), environment.get("PYTHONPATH", "")]
        )
        process = subprocess.run(
            [sys.executable, "-m", "interogare_anaf", *map(str, args)],
            cwd=ROOT, env=environment, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(
            process.returncode, expected_returncode,
            "CLI %r (exit %r):\nstdout=%s\nstderr=%s"
            % (args, process.returncode, process.stdout, process.stderr),
        )
        return process


class TestNormalizeMapping(OpenCodeExtraBase):
    def test_all_ro_diacritics_are_transliterated(self):
        self.assertEqual(
            normalize(
                "ÎNCINGĂTOAREA ȘTIINȚIFICĂ cu ţipărire în Bârzei "
                "și cu strămutare de țărâni"
            ),
            "INCINGATOAREA STIINTIFICA cu tiparire in Barzei "
            "si cu stramutare de tarani",
        )
        self.assertEqual(normalize("Căsuță"), "Casuta")
        self.assertEqual(normalize("1.11 A"), "1.11 A")
        self.assertEqual(normalize(7), 7)
        self.assertEqual(normalize(None), None)


class TestImportConflicts(OpenCodeExtraBase):
    def _csv(self, text):
        path = Path(self.tmp.name) / "import.csv"
        path.write_text(text, encoding="utf-8")
        return path

    def test_duplicate_updates_name_only_empty_name_keeps_existing(self):
        csv_path = self._csv(
            "cui;denumire_initiala\n"
            "5550001;Nume nou B SRL\n"
        )
        self.cli("init-db", "--db", self.dbpath)
        import sqlite3

        connection = sqlite3.connect(str(self.dbpath))
        try:
            connection.execute(
                "INSERT INTO parteneri (cui, denumire_initiala, denumire_anaf)"
                " VALUES (5550001, 'Nume initial A SRL', 'ANAF VECHI')"
            )
            connection.commit()
        finally:
            connection.close()

        self.cli("import-cui", "--db", self.dbpath, "--input", str(csv_path))
        import sqlite3

        connection = sqlite3.connect(str(self.dbpath))
        try:
            row = connection.execute(
                "SELECT denumire_initiala, denumire_anaf FROM parteneri"
                " WHERE cui = 5550001"
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(row, ("Nume nou B SRL", "ANAF VECHI"))

    def test_empty_name_does_not_erase_existing_and_invalids_skipped(self):
        csv_path = self._csv(
            "cui;denumire_initiala\n"
            "5550002;\n"
            "RO123;X\n"
            "-7;Y\n"
            "  ;Z\n"
            "6660001;Caz nou SRL\n"
        )
        self.cli("init-db", "--db", self.dbpath)
        import sqlite3

        connection = sqlite3.connect(str(self.dbpath))
        try:
            connection.execute(
                "INSERT INTO parteneri (cui, denumire_initiala)"
                " VALUES (5550002, 'Pastrat SRL')"
            )
            connection.commit()
        finally:
            connection.close()

        process = self.cli("import-cui", "--db", self.dbpath, "--input",
                           str(csv_path))
        self.assertIn("1 CUI importate", process.stdout)
        self.assertIn("1 duplicate", process.stdout)
        self.assertIn("3 randuri invalide", process.stdout)
        import sqlite3

        connection = sqlite3.connect(str(self.dbpath))
        try:
            kept = connection.execute(
                "SELECT denumire_initiala FROM parteneri WHERE cui = 5550002"
            ).fetchone()[0]
            inserted = connection.execute(
                "SELECT denumire_initiala FROM parteneri WHERE cui = 6660001"
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(kept, "Pastrat SRL")
        self.assertEqual(inserted, "Caz nou SRL")


class TestStrayDuplicateIncomplete(OpenCodeExtraBase):
    def test_stray_cui_ignored_duplicate_becomes_incomplet(self):
        self.cli("init-db", "--db", self.dbpath)
        import sqlite3

        connection = sqlite3.connect(str(self.dbpath))
        try:
            for cui in (1111111, 2222222, 3333333):
                connection.execute(
                    "INSERT INTO parteneri (cui, denumire_initiala)"
                    " VALUES (?, '')",
                    (cui,),
                )
            connection.commit()
        finally:
            connection.close()

        def found(denumire, cui):
            return {
                "date_generale": {"cui": cui, "denumire": denumire},
                "adresa_sediu_social": {
                    "sdenumire_Localitate": "Sibiu",
                    "sdenumire_Strada": "Str. X",
                },
            }

        body = {
            "cod": 200,
            "found": [
                found("SRL VALIDA", 1111111),
                found("SRL STRAINA", 9999999),
                found("SRL DUPLICAT", 2222222),
                found("SRL DUPLICAT", 2222222),
            ],
            "notFound": [],
        }
        with Handler.lock:
            Handler.responses.append((200, body))
        self.cli(
            "run", "--db", self.dbpath, "--date", "2026-11-02", "--api-url", self.url
        )

        import sqlite3

        connection = sqlite3.connect(str(self.dbpath))
        try:
            rows = connection.execute(
                "SELECT cui, rezultat FROM istoric_verificari ORDER BY cui"
            ).fetchall()
            valid = connection.execute(
                "SELECT denumire_anaf FROM parteneri WHERE cui = 1111111"
            ).fetchone()[0]
            stray_untouched = connection.execute(
                "SELECT denumire_anaf FROM parteneri WHERE cui = 3333333"
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(rows, [
            (1111111, "GASIT"), (2222222, "INCOMPLET"), (3333333, "INCOMPLET"),
        ])
        self.assertEqual(valid, "SRL VALIDA")
        self.assertIsNone(stray_untouched)

    def test_missing_db_reports_init_db_hint(self):
        process = self.cli(
            "run", "--db", self.dbpath, "--date", "2026-11-02",
            "--api-url", self.url, expected_returncode=2,
        )
        self.assertIn("init-db", process.stdout)

    def test_bad_date_rejected(self):
        self.cli("init-db", "--db", self.dbpath)
        process = self.cli(
            "run", "--db", self.dbpath, "--date", "02/11/2026",
            "--api-url", self.url, expected_returncode=2,
        )
        self.assertIn("YYYY-MM-DD", process.stdout)


if __name__ == "__main__":
    unittest.main()
