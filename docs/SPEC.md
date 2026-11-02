# SPEC — InterogareAnaf MVP / SQLite (istoric complet)

## 1. Obiectiv si limite

Aplicatie CLI Python 3.11+ pentru Windows si Ubuntu. Citeste CUI-uri din SQLite, interogheaza ANAF TVA v9 in loturi de cel mult 100 si actualizeaza exclusiv noua campuri ANAF din `parteneri`. Pastreaza fiecare incercare in `istoric_verificari`, fara JSON brut, date personale suplimentare sau secrete. Nu exista GUI proprie, export CSV sau alte campuri fiscale.

## 2. Persistenta SQLite

`db/schema.sql` este sursa unica si autoritativa. Schema contine exact doua tabele aplicative: `parteneri` si `istoric_verificari`.

### 2.1. `parteneri`

Pastraza exact cele 11 coloane existente, in ordinea si cu semnificatiile de mai jos. Nu adauga status, timestamp sau coloana de eroare.

| Coloana | Tip | Regula |
|---|---|---|
| `cui` | `INTEGER PRIMARY KEY` | CUI pozitiv, unic, fara `RO` |
| `denumire_initiala` | `TEXT NOT NULL DEFAULT ''` | Import initial; nu se suprascrie de raspunsul ANAF |
| `denumire_anaf` | `TEXT NULL` | `date_generale.denumire` |
| `nrRegCom` | `TEXT NULL` | `date_generale.nrRegCom`; text |
| `sdenumire_Localitate` | `TEXT NULL` | localitatea sediului social |
| `sdenumire_Strada` | `TEXT NULL` | strada sediului social |
| `snumar_Strada` | `TEXT NULL` | numarul strazii, text |
| `scod_Localitate` | `TEXT NULL` | cod localitate, text cu zerouri initiale |
| `sdenumire_Judet` | `TEXT NULL` | judetul sediului social |
| `sdetalii_Adresa` | `TEXT NULL` | detalii adresa, text |
| `scod_Postal` | `TEXT NULL` | cod postal, text cu zerouri initiale |

`NULL` indica lipsa valorii stocate; valoarea ANAF lipsa sau `""` devine `NULL`. Actualizarea unui element `found` valid seteaza toate cele noua coloane ANAF, iar `denumire_initiala` ramane neschimbata.

### 2.2. `istoric_verificari`

Tabel append-only, cu cate un rand pentru fiecare CUI trimis in fiecare cerere efectiva, inclusiv fiecare retry:

| Coloana | Tip / regula |
|---|---|
| `id` | `INTEGER PRIMARY KEY` |
| `cui` | `INTEGER NOT NULL`, FK la `parteneri(cui)` |
| `rulare_id` | `TEXT NOT NULL`, UUID comun unei executii `run` |
| `incercat_la` | `TEXT NOT NULL`, timestamp ISO 8601 UTC, terminat in `Z` |
| `data_interogarii` | `TEXT NOT NULL`, data `YYYY-MM-DD` trimisa catre ANAF |
| `nr_lot` | `INTEGER NOT NULL`, numerotare de la 1 in executia curenta |
| `nr_incercare` | `INTEGER NOT NULL`, numerotare de la 1 pentru fiecare lot |
| `rezultat` | `TEXT NOT NULL`: `GASIT`, `NEGASIT`, `EROARE` sau `INCOMPLET` |
| `http_status` | `INTEGER NULL`, cod HTTP daca a fost primit |
| `cod_eroare` | `TEXT NULL`, categorie tehnica sigura |
| `mesaj_eroare` | `TEXT NULL`, descriere fixa/sanitizata, fara date sensibile |

Schema impune rezultate valide, numere pozitive pentru lot/incercare, status HTTP in intervalul 100–599 si unicitate pentru `(rulare_id, cui, nr_lot, nr_incercare)`. Indexurile sustin cautarea dupa CUI si timp, rulare si timp.

Fiecare `run` genereaza un UUID. Fiecare incercare HTTP genereaza un timestamp UTC comun lotului si o inregistrare pentru fiecare CUI trimis. Pentru un lot de N CUI, un retry inseamna alte N randuri; randurile anterioare nu se actualizeaza sau sterg. Istoricul se pastreaza si intre executii succesive.

`init-db` aplica schema idempotent, inclusiv asupra unei baze vechi care contine deja doar `parteneri`; nu sterge si nu recreeaza date sau istoric. `db/schema.sql` nu defineste alte tabele aplicative.

## 3. Crearea si importul bazei

`init-db` creeaza directorul parinte lipsa si aplica `db/schema.sql`, folosind exclusiv biblioteca standard `sqlite3`.

`import-cui` este numai pentru popularea initiala. Citeste CSV UTF-8/BOM, separator `;`, cu antet obligatoriu `cui;denumire_initiala`; suporta peste 4.000 randuri. CUI-ul trebuie sa fie sir de cifre ASCII, pozitiv si incadrabil in INTEGER SQLite. Respinge CUI gol, `RO`, negativ, fractionar, cu litere sau depasit. Converteste CUI la `int`, elimina duplicatele prin cheia primara si normalizeaza textul initial.

La conflict, nume initial nevid inlocuieste numai `denumire_initiala`; sirul gol nu sterge numele deja stocat. Importul nu modifica campuri ANAF si nu adauga linii in istoric. Raporteaza numarul randurilor valide importate, duplicate si invalide; nu afiseaza numele firmei in loguri. Randurile invalide se omit.

Dupa import, `run` citeste exclusiv `SELECT cui FROM parteneri ORDER BY cui`. `--only-missing` continua sa selecteze exclusiv randurile cu `denumire_anaf IS NULL`; nu filtreaza pe istoric.

## 4. CLI

```text
python -m interogare_anaf init-db --db data/private/parteneri.sqlite3
python -m interogare_anaf import-cui --db data/private/parteneri.sqlite3 --input data/private/parteneri.csv
python -m interogare_anaf run --db data/private/parteneri.sqlite3 --date 2026-10-28
python -m interogare_anaf run --db data/private/parteneri.sqlite3 --date 2026-10-28 --only-missing
```

`run` suporta `--api-url URL` (implicit endpointul ANAF), `--timeout SECUNDE` (implicit 20) si `--only-missing`. `--date` este obligatoriu, calendaristic valid si in format strict `YYYY-MM-DD`; aceeasi data se trimite fiecarui CUI din toate loturile. Nici `init-db`, nici `import-cui` nu contacteaza serviciul.

Daca DB lipseste la `run` sau `import-cui`, se afiseaza instructiunea `init-db`; nu se creeaza o schema tacit. Mesajele CLI includ totaluri CUI, loturi, rezultate, erori si anomalii. Nu se persista statistici in afara istoriei definite aici.

## 5. Protocol ANAF TVA v9

- Endpoint implicit: `https://webservicesp.anaf.ro/api/PlatitorTvaRest/v9/tva`.
- HTTP `POST`, `Content-Type: application/json`.
- Corp: lista de maximum 100 obiecte `{"cui": 57449, "data": "2026-10-28"}`; CUI JSON numeric.
- CUI-urile se sorteaza si se impart in loturi consecutive de maximum 100; 4.000 CUI inseamna 40 loturi fara retry.
- Procesare secventiala, cu minimum o secunda intre inceputurile cererilor, inclusiv retry.
- Maximum 3 incercari totale pe lot. Timeout, eroare de conexiune, HTTP 429 si HTTP 5xx se reincerca cu backoff si `Retry-After` cand exista. HTTP 4xx permanent si JSON invalid nu se reincerca. Limitele de trafic se aplica fiecarui retry.
- La fiecare cerere efectuata se persista istoricul incercarii pentru fiecare CUI din lot inainte de urmatoarea incercare.
- Un lot esuat nu sterge date ANAF existente si nu impiedica procesarea loturilor urmatoare. Nicio tranzactie SQLite nu ramane deschisa in timpul asteptarii de retea.

URL-ul non-ANAF este destinat exclusiv testelor locale explicite. Testele automate si CI nu acceseaza ANAF real.

## 6. Interpretarea raspunsului si istoric

Top-level `found` si `notFound` trebuie sa fie liste. Un raspuns JSON invalid este eroare de transport/protocol (`EROARE`); raspuns cu structura top-level insuficienta este jurnalizat `INCOMPLET` pentru fiecare CUI al lotului, fara actualizare ANAF.

Pentru fiecare `found`, se identifica `date_generale.cui`, fara asociere dupa pozitia in lista. CUI-ul trebuie sa fie intreg pozitiv, inclus in lot si unic in `found`. Subobiectele `date_generale` si `adresa_sediu_social` trebuie sa fie obiecte, iar campurile selectate sa fie siruri, null sau absente. Un CUI strain, invalid, duplicat, cu aparitie simultana in ambele liste ori cu substructura de tip gresit nu se aplica. CUI-ul cerut afectat este jurnalizat `INCOMPLET`; anomalia se raporteaza.

Din `found` se citesc doar `date_generale.denumire`, `date_generale.nrRegCom` si cele sapte chei explicite din `adresa_sediu_social`. Normalizeaza diacriticele romanesti in toate valorile text. Nu preia alte sectiuni. Campurile lipsa, null sau sir gol devin `NULL`; codurile si valorile raman text pentru pastrarea zerourilor initiale.

Clasificarea pe CUI pentru fiecare raspuns HTTP valid:

- `found` valid si neambiguu: `GASIT`; actualizeaza cele noua campuri ANAF si insereaza istoricul corespunzator in aceeasi tranzactie SQLite.
- `notFound` valid si unic: `NEGASIT`; nu modifica nicio valoare ANAF existenta.
- CUI lipsa din ambele liste, afectat de anomalie sau cu structura insuficienta: `INCOMPLET`; nu modifica date ANAF.
- Timeout, conexiune, HTTP 429/5xx, HTTP 4xx permanent ori JSON invalid: `EROARE` pentru fiecare CUI al cererii, cu HTTP status daca exista, cod de categorie si mesaj sigur.

Un retry are alte randuri de istoric cu acelasi `rulare_id`/`nr_lot` si `nr_incercare` incrementat. Rezultatul final gasit/negasit/incomplet se jurnalizeaza si el pentru incercarea care a returnat raspunsul JSON. O executie urmatoare adauga randuri noi, nu rescrie istoricul.

## 7. Normalizarea textului

Pentru toate campurile text importate ori actualizate: `ă/Ă→a/A`, `â/Â→a/A`, `î/Î→i/I`, `ș/ş/Ș/Ş→s/S`, `ț/ţ/Ț/Ţ→t/T`. Nu modifica alte simboluri, punctuatia, cifrele sau spatiile semnificative; nu schimba literele in uppercase si nu comprima spatiile.

## 8. Siguranta si rezilienta

- SQL parametrizat la import, actualizare si istoric.
- Baza si fisierele SQLite/WAL/SHM locale raman ignorate de Git.
- Inainte de utilizarea cu date reale se face backup SQLite; dezvoltarea si testele nu acceseaza bazele reale.
- Un singur proces `run` pe DB; nu sunt necesare thread-uri multiple pentru clientul ANAF.
- Ctrl+C pastreaza actualizarile si istoricul tranzactiilor deja comise; lotul neterminat ramane fara date inventate.
- Datele ANAF nu se sterg la `notFound`, erori sau raspunsuri incomplete.
- Nu se persista corpul JSON integral, date fiscale necerute, date personale, credentiale sau eccezioni brute.

## 9. Testare si acceptanta

`python -m unittest discover -s tests -v` trebuie sa fie offline. Serverele simulatate asculta numai pe `127.0.0.1`; se folosesc fixture-uri fictive si network guard impotriva hosturilor externe.

Verifica cele doua tabele si coloanele exacte, init idempotent, import/duplicate/CUI invalid, normalizare, campuri lipsa, `GASIT`/`NEGASIT`/`EROARE`/`INCOMPLET`, istoric append-only intre executii, un rand pentru fiecare CUI la fiecare incercare, retry/backoff/pacing, raspunsuri HTTP si JSON invalide, raspunsuri incomplete/duplicate/straine, pastrarea datelor ANAF la erori, `--only-missing`, loturi max 100 si 4.000 CUI in 40 loturi.

Niciun test nu contacteaza serviciul ANAF real.
