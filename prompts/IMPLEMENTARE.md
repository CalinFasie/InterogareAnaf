# Prompt comun pentru Codex Windows GUI si OpenCode Ubuntu

Implementeaza complet aplicatia Python **InterogareAnaf** pe ramura deja atribuita, pe baza `docs/SPEC.md`, `db/schema.sql`, `docs/TEST_PLAN.md` si `AGENTS.md`.

Citeste aproximativ 4.000 CUI numerice din SQLite si interogheaza ANAF TVA v9 in loturi de maximum 100, cu maximum o cerere/secunda. Actualizeaza exclusiv cele noua coloane ANAF din `parteneri`; `denumire_initiala` ramane separata. Normalizeaza diacriticele romanesti in toate valorile text.

Schema autoritativa are doua tabele: `parteneri`, cu exact cele 11 coloane existente, si `istoric_verificari`. Nu adauga alte coloane sau tabele. `init-db` aplica `db/schema.sql` idempotent si adauga istoricul la baze existente fara pierderi.

Pentru fiecare cerere efectiva, scrie in istoric cate un rand pentru fiecare CUI trimis. Foloseste acelasi UUID `rulare_id` pentru executia `run`, timestamp UTC pentru `incercat_la`, `nr_lot` si `nr_incercare` deterministe si rezultatul `GASIT`, `NEGASIT`, `EROARE` ori `INCOMPLET`. Jurnalizeaza fiecare retry fara a inlocui incercarile anterioare. Actualizarea celor noua campuri si inregistrarea `GASIT` trebuie sa fie aceeasi tranzactie SQLite. La erori, pastreaza campurile ANAF anterioare. Nu persista JSON-ul brut sau informatii inutile/sensibile.

Pastreaza CLI-ul comun `init-db`, `import-cui`, `run`, toate optiunile contractuale si semantica `--only-missing` (`denumire_anaf IS NULL`). Foloseste biblioteca standard `sqlite3`; nu sunt necesare dependinte externe.

Ruleaza si repara `python -m unittest discover -s tests -v` si verificarile din `docs/TEST_PLAN.md`. Testele folosesc numai fixture-uri fictive si servere pe `127.0.0.1`; niciodata ANAF real. Inchide explicit conexiunile SQLite: context managerul nu le inchide.

Nu modifica specificatia comuna, schema sau testele de acceptanta in timpul implementarii individuale. Adauga teste suplimentare in fisiere separate.

Nu accesa baze reale ale firmei, fisiere externe repository-ului sau codul celuilalt agent. Nu face commit, merge, push, instalare globala ori interogare live fara autorizarea explicita a utilizatorului.

Codex lucreaza in proiectul Windows deja deschis prin interfata grafica. OpenCode lucreaza numai in proiectul Ubuntu deja deschis si foloseste inferenta locala configurata. Promptul si criteriile de acceptanta sunt identice pe ambele platforme.
