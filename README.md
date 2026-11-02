# InterogareAnaf

Contract comun pentru o aplicatie CLI Python 3.11+ care citeste CUI-uri din SQLite, interogheaza ANAF TVA v9 in loturi si actualizeaza numai noua campuri ANAF. Schema exacta are doua tabele: `parteneri` (11 coloane neschimbate) si `istoric_verificari` (istoric append-only pentru fiecare CUI la fiecare cerere, inclusiv retries).

## Contract si stare

- `docs/SPEC.md` — comportament complet, schema logica, transport si clasificarea istoricului.
- `db/schema.sql` — sursa unica pentru cele doua tabele, constrangeri si indexuri.
- `docs/TEST_PLAN.md` — teste comune exclusiv offline.
- `tests/test_contract.py` — suita de acceptanta comuna; nu se modifica in implementarea individuala.
- `fixtures/anaf_sintetic.json`, `fixtures/parteneri_sintetici.csv` — date fictive pentru teste.
- `prompts/IMPLEMENTARE.md`, `AGENTS.md` — instructiuni comune pentru ambele implementari.

## CLI asteptat

```text
python -m interogare_anaf init-db --db data/private/parteneri.sqlite3
python -m interogare_anaf import-cui --db data/private/parteneri.sqlite3 --input data/private/parteneri.csv
python -m interogare_anaf run --db data/private/parteneri.sqlite3 --date 2026-10-28
python -m interogare_anaf run --db data/private/parteneri.sqlite3 --date 2026-10-28 --only-missing
```

`run` mai accepta `--api-url`, `--timeout` si `--only-missing`; fara `--api-url` foloseste endpointul oficial ANAF. `--only-missing` inseamna `denumire_anaf IS NULL`, independent de istoric. `init-db` poate fi repetat si adauga tabela istoricului unei baze existente fara stergerea datelor.

## Istoric si comportament

Fiecare cerere de lot scrie cate un rand de istoric pentru fiecare CUI transmis. Rezultatele sunt `GASIT`, `NEGASIT`, `EROARE`, `INCOMPLET`; retries sunt pastrate ca incercari distincte. `rulare_id` leaga incercarile unei executii, `incercat_la` este UTC. Succesul actualizeaza cele noua coloane ANAF si inregistreaza istoricul in aceeasi tranzactie. Erorile, `notFound` si raspunsurile incomplete nu sterg valorile ANAF anterioare.

Schema nu stocheaza JSON brut si nu adauga stare sau timestamp in `parteneri`. Testele folosesc servere HTTP numai pe `127.0.0.1`; nu rula teste sau instalarea impotriva ANAF. Inaintea unei utilizari reale fa backup SQLite.

## Dezvoltare si teste

Nu sunt necesare dependinte Python externe. Creeaza un mediu virtual local cu `py -3.11 -m venv .venv` pe Windows sau `python3 -m venv .venv` pe Ubuntu. Din radacina proiectului:

```text
python -m unittest discover -s tests -v
python -m py_compile interogare_anaf/*.py
python -m interogare_anaf --help
```

Pe Windows, foloseste interpretul din `.venv\Scripts\python.exe`; pe Ubuntu, `.venv/bin/python`. Nu comite baze SQLite, CSV-uri private ori directoare `.venv`.
