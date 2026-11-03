# InterogareAnaf

Aplicație CLI Python 3.11+ pentru Windows și Ubuntu. Citește CUI-uri din SQLite, interoghează ANAF TVA v9 secvențial în loturi de cel mult 100 și actualizează doar cele nouă câmpuri ANAF selectate. Păstrează fiecare încercare în istoricul SQLite append-only.

Aplicația **nu creează și nu populează automat o bază cu date reale**. Utilizatorul trebuie să inițializeze explicit baza, să importe CSV-ul propriu și să facă backup înainte de verificarea reală. Dezvoltarea și testele proiectului folosesc exclusiv date sintetice și server HTTP local; testele nu contactează ANAF.

## Cerințe

- Windows 10/11 sau Ubuntu.
- Python 3.11 sau mai nou; pe Windows este util Python Launcher (`py`).
- Nu sunt necesare dependențe Python externe. Clientul HTTP, SQLite și CLI-ul folosesc biblioteca standard.
- Conexiune la internet doar pentru comenzile `run` îndreptate explicit către endpointul ANAF.

Verifică versiunea instalată în PowerShell:

```powershell
py -3.11 --version
```

## Instalarea mediului virtual

Din rădăcina depozitului, creează și verifică mediul:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe --version
```

Nu activa mediul dacă preferi să folosești calea completă de mai sus. Toate exemplele Windows folosesc interpretul proiectului.

## Inițializarea bazei locale

Alege o cale privată pentru baza SQLite. Comanda creează schema, nu adaugă parteneri și nu contactează ANAF:

```powershell
New-Item -ItemType Directory -Force data\private | Out-Null
.\.venv\Scripts\python.exe -m interogare_anaf init-db --db data\private\parteneri.sqlite3
```

Poți rula `init-db` din nou în siguranță; datele și istoricul existente se păstrează. Dacă baza lipsește la `import-cui` sau `run`, aplicația cere inițializarea explicită și nu creează tacit o bază nouă.

## Formatul CSV și importul inițial

Fișierul trebuie să fie UTF-8 sau UTF-8 cu BOM, cu separator `;` și antetul exact `cui;denumire_initiala`. Fiecare CUI trebuie să conțină numai cifre ASCII, să fie pozitiv și să încapă în INTEGER SQLite. Prefixul `RO`, semnul, fracțiile, textul și valorile peste limita SQLite sunt respinse. Rândurile invalide sunt sărite fără a afecta rândurile valide.

Exemplu sintetic de format (CUI-urile sunt doar exemple de structură):

```powershell
@'
cui;denumire_initiala
900000001;Firma exemplu unu
900000002;Firma exemplu doi
'@ | Set-Content -Encoding utf8 data\private\parteneri.csv
```

Importă fișierul pregătit de utilizator:

```powershell
.\.venv\Scripts\python.exe -m interogare_anaf import-cui --db data\private\parteneri.sqlite3 --input data\private\parteneri.csv
```

Raportul arată câte rânduri au fost procesate, duplicate și invalide; nu afișează denumirile. La o eroare de import, rândurile invalide sunt omise, iar cele valide sunt păstrate. Un nume inițial nevid actualizează numai `denumire_initiala`; un nume gol nu șterge valoarea existentă. Importul nu scrie câmpuri ANAF și nu adaugă istoric.

Pentru aproximativ 4.000 de CUI-uri, pregătește CSV-ul cu același antet și câte un rând pentru fiecare partener, apoi rulează aceeași comandă `import-cui`. Aplicația citește ulterior CUI-urile ordonate din SQLite și le împarte în cel mult 100 per cerere (40 loturi pentru exact 4.000 de CUI-uri).

## Backup înainte de verificare

Închide orice alt proces care folosește baza. Creează un director privat și folosește API-ul SQLite backup, care copiază în siguranță baza chiar dacă SQLite folosește jurnalizare:

```powershell
New-Item -ItemType Directory -Force data\private\backups | Out-Null
.\.venv\Scripts\python.exe -c "import sqlite3; src=sqlite3.connect('data/private/parteneri.sqlite3'); dst=sqlite3.connect('data/private/backups/parteneri-pre-run.sqlite3'); src.backup(dst); dst.close(); src.close()"
```

Folosește un nume nou pentru fiecare copie, de exemplu cu data și ora în nume, și verifică existența backupului înainte de a continua. Baza, CSV-urile private și copiile SQLite sunt excluse din Git prin `.gitignore`.

## Executarea verificărilor

`--date` este obligatoriu și trebuie să fie o dată calendaristică validă în format strict `YYYY-MM-DD`. Exemplu PowerShell cu data curentă:

```powershell
$queryDate = Get-Date -Format 'yyyy-MM-dd'
.\.venv\Scripts\python.exe -m interogare_anaf run --db data\private\parteneri.sqlite3 --date $queryDate
```

Aplicația folosește endpointul ANAF implicit. Fiecare cerere conține maximum 100 CUI-uri, cererile sunt secvențiale și încep la cel puțin o secundă distanță. Timeoutul implicit este 20 de secunde; poate fi schimbat cu o valoare finită pozitivă:

```powershell
.\.venv\Scripts\python.exe -m interogare_anaf run --db data\private\parteneri.sqlite3 --date $queryDate --timeout 30
```

`--api-url` permite un endpoint alternativ și este destinat testării controlate, de exemplu către un server local simulat:

```powershell
.\.venv\Scripts\python.exe -m interogare_anaf run --db data\private\parteneri.sqlite3 --date $queryDate --api-url http://127.0.0.1:8765/fake/tva
```

Nu folosi un URL alternativ necunoscut cu date de parteneri.

## Reluarea și `--only-missing`

La `Ctrl+C`, procesul se oprește cu codul 130; tranzacțiile loturilor deja comise și istoricul lor rămân în bază. După ce verifici baza și creezi un backup nou, poți relua numai partenerii pentru care `denumire_anaf IS NULL`:

```powershell
$queryDate = Get-Date -Format 'yyyy-MM-dd'
.\.venv\Scripts\python.exe -m interogare_anaf run --db data\private\parteneri.sqlite3 --date $queryDate --only-missing
```

Acesta este exact criteriul opțiunii: `--only-missing` selectează în continuare și rândurile care au deja încercări `EROARE`, `NEGASIT` sau `INCOMPLET`, dacă denumirea ANAF este încă `NULL`. Nu deduce starea din istoric. Dacă un răspuns `GASIT` nu conține denumire, coloana rămâne `NULL` și rândul va fi selectat din nou.

## Verificarea rezultatelor și istoricului

`parteneri` are exact 11 coloane; denumirea inițială este păstrată separat de cea ANAF. Cele nouă valori ANAF sunt normalizate pentru diacritice românești, iar câmpurile lipsă, `null` sau goale devin `NULL`. `notFound`, erorile și răspunsurile incomplete nu șterg date ANAF anterioare.

Pentru o verificare rapidă de consistență, rulează:

```powershell
.\.venv\Scripts\python.exe -c "import sqlite3; db=sqlite3.connect('data/private/parteneri.sqlite3'); print('integrity_check:', db.execute('PRAGMA integrity_check').fetchone()[0]); print('parteneri:', db.execute('SELECT COUNT(*) FROM parteneri').fetchone()[0]); print('istoric:', db.execute('SELECT COUNT(*) FROM istoric_verificari').fetchone()[0]); db.close()"
```

Istoricul conține fiecare CUI trimis la fiecare încercare, inclusiv codurile HTTP și rezultate `GASIT`, `NEGASIT`, `EROARE` și `INCOMPLET`. Poți interoga ultimele încercări cu Python și SQLite:

```powershell
.\.venv\Scripts\python.exe -c "import sqlite3; db=sqlite3.connect('data/private/parteneri.sqlite3'); [print(row) for row in db.execute('SELECT cui, rulare_id, incercat_la, data_interogarii, nr_lot, nr_incercare, rezultat, http_status, cod_eroare, mesaj_eroare FROM istoric_verificari ORDER BY id DESC LIMIT 20')]; db.close()"
```

## Interpretarea erorilor

- HTTP 429 și 5xx, timeouturile și erorile de conexiune sunt reîncercate până la trei încercări totale. Se respectă `Retry-After` numeric sau HTTP-date; altfel se folosește backoff.
- HTTP 4xx permanente și JSON invalid nu se reîncearcă. Lotul este jurnalizat cu rezultat `EROARE`, datele ANAF existente se păstrează, apoi procesarea continuă cu loturile următoare.
- Listele `found` și `notFound` lipsă ori cu tip invalid produc `INCOMPLET`. Intrări duplicate, contradictorii, străine, cu substructuri invalide ori CUI-uri neasociate în siguranță nu suprascriu datele.
- Un mesaj despre lot eșuat după epuizarea retry-urilor duce la cod de ieșire `1`. Oprirea prin `Ctrl+C` duce la codul `130`. Erorile de utilizare sau bază sunt afișate fără a persista corpul JSON ori răspunsuri brute.

Nu există export automat sau GUI. Pentru auditul datelor, interoghează local baza SQLite și istoricul; păstrează copii de siguranță în locație privată.

## Dezvoltare și teste offline

Contractul este definit în `docs/SPEC.md`, schema autoritativă în `db/schema.sql`, iar cazurile comune în `docs/TEST_PLAN.md`. Testele folosesc fixture-uri fictive și servere legate numai la `127.0.0.1`; niciun test nu contactează ANAF real.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q interogare_anaf tests
.\.venv\Scripts\python.exe -m interogare_anaf --help
```

Pe Ubuntu folosește `python3 -m venv .venv`, apoi `.venv/bin/python` pentru comenzile de mai sus. Nu comite baze SQLite, CSV-uri cu date reale, răspunsuri ANAF, backupuri sau credențiale.
