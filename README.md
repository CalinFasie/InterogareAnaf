# InterogareAnaf

Aplicatie CLI Python 3.11+ care citeste CUI-uri din SQLite, interogheaza ANAF TVA v9 in loturi si actualizeaza numai cele noua campuri ANAF din `parteneri`. Schema are doua tabele: `parteneri` cu exact 11 coloane neschimbate si `istoric_verificari` pentru istoricul append-only al fiecarei incercari.

## Instalare locala

Nu sunt necesare dependinte Python externe. Din radacina repository-ului:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe --version
```

Pe Ubuntu:

```bash
python3 -m venv .venv
.venv/bin/python --version
```

Ruleaza comenzile din radacina proiectului cu interpretul din mediul virtual. Instalarea, `init-db` si `import-cui` nu contacteaza ANAF.

## CLI

```text
python -m interogare_anaf init-db --db data/private/parteneri.sqlite3
python -m interogare_anaf import-cui --db data/private/parteneri.sqlite3 --input data/private/parteneri.csv
python -m interogare_anaf run --db data/private/parteneri.sqlite3 --date 2026-10-28
python -m interogare_anaf run --db data/private/parteneri.sqlite3 --date 2026-10-28 --only-missing
```

Inlocuieste `python` cu `.venv\Scripts\python.exe` pe Windows sau `.venv/bin/python` pe Ubuntu. CSV-ul este UTF-8 ori UTF-8 BOM, cu separator `;` si antet `cui;denumire_initiala`. Randurile invalide se omit si se raporteaza fara numele firmei; un nume initial gol nu sterge numele deja stocat.

`run` accepta `--api-url URL` (implicit endpointul oficial), `--timeout SECUNDE` (implicit 20) si `--only-missing`. Ultima optiune selecteaza numai randurile cu `denumire_anaf IS NULL`, independent de istoric. Loturile au cel mult 100 CUI, cu minimum o secunda intre inceputurile cererilor. Clientul reincerca maximum de doua ori pentru timeout, erori de conexiune, HTTP 429 si HTTP 5xx, cu backoff si `Retry-After`.

## Istoric si limite

Fiecare cerere efectiva scrie cate un rand in `istoric_verificari` pentru fiecare CUI din lot. Rezultatele sunt `GASIT`, `NEGASIT`, `EROARE` si `INCOMPLET`; fiecare retry si fiecare executie `run` se pastreaza separat. Succesul actualizeaza cele noua coloane ANAF si adauga istoricul in aceeasi tranzactie SQLite. `notFound`, erorile si raspunsurile incomplete nu sterg valorile ANAF anterioare.

`parteneri` nu contine status sau data verificarii. `--only-missing` nu deduce starea din istoric. Nu se pastreaza JSON-ul integral ANAF ori alte campuri fiscale. Inainte de o rulare reala, fa un backup SQLite.

## Contract si teste

- `docs/SPEC.md` — contractul functional si protocolul istoricului.
- `db/schema.sql` — sursa unica pentru tabele, constrangeri si indexuri.
- `docs/TEST_PLAN.md` si `tests/test_contract.py` — acceptanta comuna offline.
- `fixtures/anaf_sintetic.json`, `fixtures/parteneri_sintetici.csv` — date fictive.
- `AGENTS.md`, `prompts/IMPLEMENTARE.md` — instructiuni comune pentru Codex si OpenCode.

Ruleaza `python -m unittest discover -s tests -v`. Testele HTTP folosesc numai servere pe `127.0.0.1` si nu contacteaza ANAF. Pe Windows, foloseste `.venv\Scripts\python.exe`; pe Ubuntu, `.venv/bin/python`. Nu comite baze SQLite, CSV-uri private ori directoare `.venv`.
