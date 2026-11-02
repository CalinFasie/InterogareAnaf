# InterogareAnaf

Aplicatie Python 3.11+ pentru importul CUI-urilor intr-o baza SQLite si actualizarea celor noua campuri selectate din raspunsul ANAF TVA v9. Schema are exact 11 coloane si este definita in `db/schema.sql`; nu sunt stocate alte date ANAF.

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

Comenzile se ruleaza din radacina proiectului folosind interpretul din mediul virtual. Aplicatia nu interogheaza ANAF la instalare sau la `init-db`/`import-cui`.

## CLI

```text
python -m interogare_anaf init-db --db data/private/parteneri.sqlite3
python -m interogare_anaf import-cui --db data/private/parteneri.sqlite3 --input data/private/parteneri.csv
python -m interogare_anaf run --db data/private/parteneri.sqlite3 --date 2026-10-28
python -m interogare_anaf run --db data/private/parteneri.sqlite3 --date 2026-10-28 --only-missing
```

Inlocuieste `python` cu `.venv\Scripts\python.exe` pe Windows sau `.venv/bin/python` pe Ubuntu. CSV-ul de import este UTF-8 ori UTF-8 BOM, cu separator `;` si antet `cui;denumire_initiala`. Randurile invalide se omit si se raporteaza fara a afisa numele firmei. Un nume initial gol la import nu sterge un nume deja stocat.

`run` accepta si `--api-url URL` pentru servere de test explicite si `--timeout SECUNDE` (implicit 20). Fara `--api-url`, foloseste endpointul oficial. Loturile sunt sortate, de maximum 100 CUI; clientul limiteaza inceputul cererilor la cel mult una pe secunda si reincerca de cel mult doua ori dupa prima incercare pentru timeout, erori de conexiune, HTTP 429 si HTTP 5xx. Testele folosesc loopback si nu contacteaza endpointul oficial.

Inaintea unei rulari reale, fa un backup al bazei. `run` citeste CUI-urile numai din SQLite; `--only-missing` selecteaza randurile cu `denumire_anaf IS NULL`.

## Limita de stare

Schema nu are coloana de status sau data verificarii. Prin urmare, baza nu poate deosebi un CUI care nu a fost interogat de unul returnat in `notFound`, si nu poate arata cand s-a facut ultima verificare. `notFound` nu modifica datele ANAF existente; `--only-missing` il poate interoga din nou, la fel ca un rand `found` fara denumire. Aceasta limitare este pastrata intentionat pentru schema de 11 coloane.

## Teste offline

```bash
python -m unittest discover -s tests -v
```

Testele HTTP folosesc doar servere pe `127.0.0.1` si fixture-ul sintetic. Nu ruleaza `run` cu endpointul oficial.
