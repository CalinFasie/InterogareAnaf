# TEST_PLAN — criterii comune de acceptanta, fara apeluri ANAF reale

## Reguli

1. `python -m unittest discover -s tests -v` ruleaza offline, numai cu server HTTP simulat pe `127.0.0.1`; un guard interzice conexiuni externe pentru procesele CLI testate.
2. `fixtures/anaf_sintetic.json` contine date fictive, dar reproduce structura `date_generale`, `adresa_sediu_social`, `found`, `notFound`.
3. `57449.json` este un exemplu real local pus la dispozitie separat de utilizator; nu se publica in GitHub.
4. Agentii nu modifica suita comuna. Pot adauga teste in alte fisiere.

## Cazuri obligatorii

| ID | Test | Rezultat asteptat |
|---|---|---|
| T01 | `init-db` pe cale inexistenta | Creeaza DB si exact tabela `parteneri` cu 11 coloane |
| T02 | `init-db` repetat | Pastreaza toate randurile |
| T03 | `import-cui` cu CSV fictiv | CUI `INTEGER`, denumiri initiale normalizate |
| T04 | CUI duplicat in import | Nu dubleaza randurile, nu sterge date ANAF existente |
| T05 | CUI invalid (gol, negativ, `RO`, fractional, litere) | Respinge randul si raporteaza eroarea |
| T06 | `found` pentru un CUI | Actualizeaza numai cele 9 coloane ANAF aferente |
| T07 | `notFound` pentru un CUI | Nu schimba coloanele ANAF, raporteaza in consola |
| T08 | Diacritice `ăâîșşțţ` si uppercase | Normalizate in caractere latine, inclusiv denumirea initiala |
| T09 | Cod postal/localitate `001234`/`000316` | Zerourile de la inceput se pastreaza |
| T10 | `denumire_initiala` diferita de ANAF | Ambele valori raman separate |
| T11 | Chei ANAF lipsa/sir gol | Coloana lipsa ramane `NULL` dupa `found` valid |
| T12 | `found` cu CUI strain, duplicat sau invalid | Nu modifica alt CUI; anomalie raportata |
| T13 | HTTP 429/5xx/timeout | Maximum 3 incercari per lot, pacing si backoff |
| T14 | HTTP 4xx permanent sau JSON invalid | Nu sterge valori, continua cu celelalte loturi |
| T15 | Lista `found`/`notFound` incompleta | Nu inventeaza valori; raporteaza CUI nerezolvate |
| T16 | 101 CUI | Cel putin doua cereri, fiecare cu maximum 100 |
| T17 | 4.000 CUI | 40 loturi fara retry, nu 4.000 apeluri individuale |
| T18 | Limita de trafic | Minimum o secunda intre inceputurile a doua cereri, inclusiv retry |
| T19 | Reexecutare `run` | Rezultate actualizate, denumirea initiala neschimbata |
| T20 | `--only-missing` | Interogheaza doar randuri cu `denumire_anaf IS NULL` |
| T21 | Oprire dupa mai multe loturi | Datele deja salvate persista, nu corupe DB |
| T22 | Raspuns cu alte sectiuni fiscale | Niciun camp suplimentar nu apare in SQLite |

Suita inclusa automatizeaza cazurile esentiale de schema, `init-db`, `import-cui`, mapare, normalizare, `found`, `notFound`, `--only-missing` si transport numai local. Cazurile de failover/pacing la 4.000 CUI pot necesita teste suplimentare ale agentilor; nu se declara trecute fara rulare efectiva.

## Verificare dupa codare

```bash
python -m unittest discover -s tests -v
```

Un esec de tip `No module named interogare_anaf` inaintea implementarii este asteptat: baseline-ul nu include codul aplicatiei.
