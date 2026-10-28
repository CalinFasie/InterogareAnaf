# SPEC — InterogareAnaf MVP / SQLite (revizia 2026-10-28)

## 1. Obiectiv si limite de domeniu

Aplicatie de linie de comanda in Python 3.11+ pentru Windows si Ubuntu. Citeste CUI-uri numerice dintr-o baza SQLite si completeaza **doar** campurile alese de utilizator din raspunsul ANAF TVA v9. Aproximativ 4.000 de CUI-uri. Fara aplicatie GUI proprie, fara raport CSV de iesire, fara alte campuri fiscale.

**Codex este utilizat din interfata grafica pe Windows**; aceasta alegere nu obliga aplicatia dezvoltata sa aiba GUI. Pe Ubuntu se foloseste OpenCode cu inferenta locala (daca mediul Ollama/OpenCode este deja functional).

Contractul acesta este comun si nu poate fi modificat de cei doi agenti in timpul comparatiei.

## 2. Persistenta: un singur tabel cu 11 coloane

Schema exacta si autoritativa se afla in `db/schema.sql`. Tabela: `parteneri`.

| Coloana SQLite | Tip | Sursa | Regula |
|---|---|---|---|
| `cui` | `INTEGER PRIMARY KEY` | date initiale; corespondenta cu `date_generale.cui` | CUI pozitiv, unic, fara `RO` |
| `denumire_initiala` | `TEXT NOT NULL DEFAULT ''` | import initial | Nu se suprascrie la interogarea ANAF |
| `denumire_anaf` | `TEXT NULL` | `date_generale.denumire` | Normalizeaza diacriticele |
| `nrRegCom` | `TEXT NULL` | `date_generale.nrRegCom` | Pastreaza formatul ca text |
| `sdenumire_Localitate` | `TEXT NULL` | `adresa_sediu_social.sdenumire_Localitate` | Text transliterat |
| `sdenumire_Strada` | `TEXT NULL` | `adresa_sediu_social.sdenumire_Strada` | Text transliterat |
| `snumar_Strada` | `TEXT NULL` | `adresa_sediu_social.snumar_Strada` | Text; poate contine litere |
| `scod_Localitate` | `TEXT NULL` | `adresa_sediu_social.scod_Localitate` | Text; pastreaza zerourile de inceput |
| `sdenumire_Judet` | `TEXT NULL` | `adresa_sediu_social.sdenumire_Judet` | Text transliterat |
| `sdetalii_Adresa` | `TEXT NULL` | `adresa_sediu_social.sdetalii_Adresa` | Text transliterat; pastreaza punctuatia si spatiile |
| `scod_Postal` | `TEXT NULL` | `adresa_sediu_social.scod_Postal` | Text; pastreaza zerourile de inceput |

Nu se creeaza alte tabele ori coloane (`status`, `verificat_la`, `data_interogarii`, `eroare`, `platitor_tva` etc.). Este permisa utilizarea de variabile temporare in memorie si afisarea de contoare/erori in consola; nu se persista metadatele.

`NULL` pentru un camp ANAF indica lipsa unei valori stocate. Un sir gol `""` din raspunsul ANAF este convertit la `NULL`. `denumire_initiala` poate fi `''` cand este cunoscut numai CUI-ul.

## 3. Crearea si alimentarea bazei

`init-db`: creeaza directorul parinte cand lipseste si aplica `db/schema.sql` pe DB indicata; daca baza exista, nu elimina continutul. Se foloseste `sqlite3` din biblioteca standard Python; nu presupunem existenta executabilului `sqlite3` pe Ubuntu.

`import-cui`: comanda **auxiliara de populare initiala**, nu o sursa pentru executarea interogarilor. Citeste UTF-8 sau UTF-8 BOM, separator `;`, antet obligatoriu `cui;denumire_initiala`, 1-4.000+ randuri. `cui` este numai un sir de cifre care se incadreaza intr-un `INTEGER` pozitiv SQLite. Nu se accepta `RO`, cifre fractionare, CUI gol sau valori negative. Se transforma in `int`, se elimina duplicatele prin cheia primara. Importul nu sterge valorile ANAF deja stocate. La conflict pe CUI, un `denumire_initiala` nevid din CSV actualizeaza numai aceasta coloana; sirul gol nu sterge o denumire initiala existenta. Se numara importurile, duplicatele si randurile invalide. Randurile invalide sunt raportate si sarite; numele de firma nu se afiseaza integral in loguri.

Dupa import, executia `run` citeste **exclusiv** `SELECT cui FROM parteneri ORDER BY cui`, nu mai deschide CSV-ul.

## 4. CLI stabil (testabil identic in cele doua variante)

```bash
python -m interogare_anaf init-db --db data/private/parteneri.sqlite3
python -m interogare_anaf import-cui --db data/private/parteneri.sqlite3 --input data/private/parteneri.csv
python -m interogare_anaf run --db data/private/parteneri.sqlite3 --date 2026-10-28
python -m interogare_anaf run --db data/private/parteneri.sqlite3 --date 2026-10-28 --only-missing
```

Optiuni suplimentare pentru `run`:

- `--api-url URL`: endpoint configurabil, obligatoriu de suportat pentru testele offline cu server local. Valoarea implicita este endpointul oficial ANAF. Folosirea unui URL non-ANAF este doar pentru testare explicita.
- `--timeout SECUNDE`: timeout pe cerere (valoare implicita recomandata: 20 secunde).
- `--only-missing`: selecteaza exclusiv randurile pentru care `denumire_anaf IS NULL`. Fara optiune: reinterogheaza toate CUI-urile, in scop de actualizare.
- `--date`: data calendaristica reala, in format `YYYY-MM-DD`, obligatorie pentru interogari reproductibile; aceeasi data se trimite pentru fiecare CUI.

Nici `init-db`, nici `import-cui` nu contacteaza ANAF. `run` nu este apelat automat de instalare sau teste; verificarea live este initiata explicit de utilizator.

## 5. Protocol ANAF

- Endpoint: `https://webservicesp.anaf.ro/api/PlatitorTvaRest/v9/tva`.
- Metoda: `POST`, `Content-Type: application/json`.
- Corp: o lista JSON cu obiecte `{"cui": 57449, "data": "2026-10-28"}` (CUI JSON numeric, data text).
- Maximum **100 CUI** pe cerere; maximum **o cerere/secunda per client**. Se foloseste procesare secventiala, cu interval de minimum 1 secunda intre inceputurile cererilor, inclusiv reincer carile.
- Sortare dupa CUI si impartire in loturi consecutive de max. 100; pentru 4.000 de CUI => 40 loturi fara reincer cari.
- Retry pentru timeout, erori de conexiune, HTTP 429 si HTTP 5xx: maximum 3 incercari in total pe lot, cu backoff si `Retry-After` cand e prezent; limitele de trafic se aplica si reincercarilor. HTTP 4xx permanent (exceptie 429) si raspuns JSON invalid sunt erori raportate, fara a compromite celelalte loturi.
- Un lot esuat nu sterge randuri actualizate anterior. Nu se tine o tranzactie SQLite deschisa in asteptarea retelei.
- Nu sunt permise apeluri ANAF reale in teste automate sau GitHub Actions.

Documentatie oficiala ANAF: https://static.anaf.ro/static/10/Anaf/Informatii_R/Servicii_web/doc_WS_V9.txt (instructiuni v9 publicate la 04.02.2025).

## 6. Interpretarea raspunsului

Exemplul real de referinta primit de la utilizator este `57449.json`. El este **referinta locala**, nu trebuie inclus in repository public. In baseline avem `fixtures/anaf_sintetic.json`, cu forma similara si CUI fictiv.

Pentru fiecare element din `found`:

1. Identifica `date_generale.cui` si verifica faptul ca apare in lotul trimis. Nu asocia randuri dupa ordinea din raspuns.
2. Citeste doar `date_generale.denumire`, `date_generale.nrRegCom` si cele 7 chei numite explicit din `adresa_sediu_social`.
3. Converteste diacriticele romanesti in corespondente latine; nu modifica alte informatii si nu elimina punctuatia, cifrele ori spatiile semnificative.
4. Pe un element `found` valid, actualizeaza atomic **doar** cele 9 coloane ANAF aferente acelui CUI. Daca o cheie lipseste sau contine sir gol, seteaza coloana respectiva la `NULL`. `denumire_initiala` ramane neschimbata.
5. Daca `date_generale.cui` lipseste, este invalid, nu apare in lot sau este duplicat intr-un raspuns, ignora acele elemente si raporteaza anomalie. Daca subobiectele necesare sunt de tip gresit, ignora elementul, nu scrie valori arbitrare.

Pentru `notFound`: identifica CUI-urile returnate, raporteaza numarul lor si **nu modifica** datele ANAF deja existente. Nu considera `notFound` drept rezultat negativ fiscal si nu adauga o coloana de status.

Pentru CUI-uri care lipsesc simultan din `found` si `notFound`, raporteaza raspunsul incomplet; nu actualizeaza randurile respective. Nu procesa campuri necerute (`adresa`, `codPostal`, `adresa_domiciliu_fiscal`, `inregistrare_scop_Tva`, `stare_inactiv`, `RO e-Factura`, etc.). Daca raspunsul este eronat sau incomplet ca structura, nu suprascrie datele anterioare ale lotului.

### Consecinta explicita a schemei fara status

Nu putem deosebi persistent un CUI niciodata interogat de unul prezent in `notFound`, deoarece nu avem coloane de stare/date. `--only-missing` reinterogheaza randurile pentru care `denumire_anaf IS NULL`, inclusiv `notFound` si `found` fara denumire. Nu putem deduce din SQLite *cand* s-a efectuat ultima verificare. Aceste limitari sunt **acceptate pentru MVP**, ca sa respectam cerinta celor 11 coloane.

## 7. Normalizarea diacriticelor

Obligatoriu pentru **toate** campurile text inserate/actualizate, inclusiv `denumire_initiala` la import:

`ă→a`, `Ă→A`, `â→a`, `Â→A`, `î→i`, `Î→I`, `ș/ş→s`, `Ș/Ş→S`, `ț/ţ→t`, `Ț/Ţ→T`.

Se poate folosi `unicodedata.normalize('NFD', value)` urmat de eliminarea semnelor combinatorii pentru caracterele romanesti (sau o mapare explicita), fara a distruge alte simboluri. Nu se impune conversie la uppercase, eliminarea dublelor spatii sau schimbarea punctuatiei.

Exemplu din fisierul real: `ÎN INCINTA PARCULUI ȘTIINȚIFIC ȘI TEHNOLOGIC  BIHOR. SPAȚIU BIROU NR. 1.11` devine `IN INCINTA PARCULUI STIINTIFIC SI TEHNOLOGIC  BIHOR. SPATIU BIROU NR. 1.11`.

## 8. Siguranta si rezilienta

- SQL numai cu parametri la import si UPDATE, niciodata concatenare de valori.
- DB in `data/private/parteneri.sqlite3`, ignorata de Git; acelasi lucru pentru orice backup sau fisiere SQLite WAL/SHM.
- Inainte de verificarea live, utilizatorul efectueaza backup SQLite (se recomanda API-ul `sqlite3.Connection.backup`).
- Un proces de interogare pe DB odata; nu sunt necesare thread-uri multiple pentru API.
- Inchidere controlata la Ctrl+C: loturile deja salvate raman, cele neterminate raman neatinse.
- Daca DB nu exista la `run` sau `import-cui`, afiseaza o eroare clara cu instructiunea `init-db` (nu crea tacit un tabel gresit).
- Mesaje CLI cu total CUI citite, loturi procesate, CUI gasite, negasite, raspunsuri incomplete si loturi esuate; fara persistarea acestora in tabel.
- `run` trebuie sa poata fi repetat in siguranta. Datele obtinute cu succes sunt suprascrise doar in coloanele ANAF, pastrand denumirea initiala.

## 9. Testare si acceptanta

Se executa suita de acceptanta comuna `python -m unittest discover -s tests -v` si testele suplimentare implementate de fiecare agent; nu se modifica testele comune. Serverul HTTP de test asculta numai pe `127.0.0.1`; nu se contacteaza ANAF in teste.

Cazuri obligatorii: schema cu exact 11 coloane; import/duplicate/CUI invalid; doua denumiri independente; parsare `found` si `notFound`; nume si adrese cu diacritice; coduri cu zerouri; lipsa de campuri; erori HTTP 429/5xx/timeout/JSON invalid; loturi de max. 100 si pacing de max. 1 request/s; procesare continua cand un lot esueaza; reintrare `--only-missing`; raspuns cu CUI strain in `found`; 4.000 CUI fara a depasi limitele.

Doi agenti primesc acelasi baseline, aceeasi data de test, acelasi prompt si aceleasi teste; nu se executa merge intre ramuri inaintea evaluarii.

## 10. In afara scopului

Nu exista UI proprie, CSV export, coloane fiscale TVA/e-Factura, campuri din adresa domiciliului fiscal, audit istoric, rulare programata, acces concurent la DB sau integrare cu sisteme interne.
