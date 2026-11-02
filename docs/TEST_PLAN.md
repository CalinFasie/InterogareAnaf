# TEST_PLAN — contract comun SQLite cu istoric, fara apeluri ANAF reale

## Reguli

1. Comanda de acceptanta este `python -m unittest discover -s tests -v` si trebuie sa ruleze offline.
2. HTTP-ul de test foloseste numai servere locale legate la `127.0.0.1`; fixture-urile sunt fictive, iar network guard-ul blocheaza hosturile externe pentru CLI.
3. Nu se modifica modulul comun de schema sau testele contractuale in timpul implementarii agentilor; testele suplimentare se adauga separat.
4. Toate conexiunile SQLite deschise de teste se inchid explicit, inclusiv cand folosesc blocuri `with`; context managerul conexiunii nu este un substitut pentru `close()`.
5. Niciun test nu face cereri catre serviciul ANAF real.

## Acceptanta comuna

| ID | Verificare | Rezultat asteptat |
|---|---|---|
| T01 | Schema aplicata din `db/schema.sql` | Exact tabelele `parteneri`, `istoric_verificari`; fara alte tabele aplicative |
| T02 | Structura `parteneri` | Exact cele 11 coloane contractuale, in ordinea existenta; `cui` INTEGER PK pozitiv |
| T03 | Structura istoriei | Exact campurile contractuale, FK, rezultat constrans, unicitate si indexuri pentru CUI/rulare/timp |
| T04 | `init-db` pe cale absenta si repetat | Creeaza directoare/tabele; nu sterge randuri sau istoric existent |
| T05 | Import CSV valid si diacritice | CUI INTEGER; text normalizat; denumirea initiala ramane independenta |
| T06 | Duplicate si CUI invalid | Fara randuri duplicate; campuri ANAF pastrate; invalidurile raportate si sarite |
| T07 | Raspuns `found` valid | Numai cele 9 campuri ANAF se actualizeaza; un istoric `GASIT`; operatie si istoric aceeasi tranzactie |
| T08 | Raspuns `notFound` | Istoric `NEGASIT`; date ANAF existente neschimbate |
| T09 | Chei ANAF lipsa/null/gol | `NULL` doar pentru campurile lipsa dintr-un `found` valid; codurile text pastreaza zerourile initiale |
| T10 | Date structurale lipsa, CUI absent/strain/invalid/duplicat/conflict | `INCOMPLET` pentru CUI-urile cerute afectate; date ANAF nemodificate; anomalii raportate |
| T11 | HTTP 4xx permanent, 429, 5xx, timeout, conexiune si JSON invalid | `EROARE` pe fiecare CUI si fiecare cerere incercata; retry doar pentru clasele tranzitorii, max. 3 incercari |
| T12 | Retry al lotului | Fiecare retry adauga un rand per CUI cu `nr_incercare` corect; inregistrarile anterioare nu se rescriu |
| T13 | Raspuns incomplet | CUI omis/substructura invalida are `INCOMPLET`; rezultatele valide ale celorlalte CUI nu se asociaza gresit |
| T14 | Istoric peste executii `run` | UUID-uri distincte; toate randurile anterioare se pastreaza |
| T15 | Eroare dupa o actualizare reusita | Campurile ANAF raman intacte; erorile se adauga numai in istoric |
| T16 | `--only-missing` | Selecteaza tot si numai CUI-urile cu `denumire_anaf IS NULL`; nu consulta istoricul pentru filtrare |
| T17 | Limita lot si 101 CUI | Nicio cerere peste 100; 101 CUI implica doua loturi |
| T18 | 4.000 CUI | 40 loturi fara retry, nu 4.000 cereri individuale |
| T19 | Pacing | Inceputurile HTTP la minimum 1 secunda, inclusiv retry |
| T20 | Alte sectiuni din fixture | Nu persista date suplimentare si nu extinde schema |
| T21 | Erori de conectare/oprire | Continua cu loturile urmatoare; tranzactiile si istoricul deja comise raman valide |

## Verificari de rulare

```text
python -m unittest discover -s tests -v
python -m py_compile interogare_anaf/*.py
python -m interogare_anaf --help
git diff --check
```

Testele care necesita un interval real de pacing trebuie sa aiba timeout suficient. Pentru cazurile de volum mare, fixture-ul se poate furniza de serverul local; se verifica numarul efectiv de cereri si continutul lor. Rezultatele se raporteaza separat pentru cazurile care nu au putut fi rulate; nu se declara succes fara executie.
