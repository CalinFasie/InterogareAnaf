# Prompt comun pentru Codex Windows GUI si OpenCode Ubuntu

Implementeaza complet aplicatia Python **InterogareAnaf**, pe ramura de Git deja activa, pe baza fisierelor `docs/SPEC.md`, `db/schema.sql`, `docs/TEST_PLAN.md` si `AGENTS.md`.

Obiectiv: aproximativ 4.000 CUI numerice citite din SQLite; pentru fiecare CUI se interogheaza prin loturi serviciul ANAF TVA v9 si se actualizeaza exclusiv 9 campuri ANAF din tabela `parteneri` (denumire, `nrRegCom`, 7 campuri ale sediului social). `denumire_initiala` ramane distincta. Nu adauga coloane ori tabele si nu prelua alte sectiuni ANAF. Normalizeaza diacriticele romanesti in toate campurile text.

Sarcini:

1. Inspecteaza repository-ul, confirmarile de ramura si structura baseline-ului.
2. Creeaza pachetul Python `interogare_anaf` cu CLI-ul comun: `init-db`, `import-cui`, `run`; respecta toate optiunile contractuale.
3. Utilizeaza `sqlite3` pentru persistenta si `db/schema.sql` ca sursa unica a schemei.
4. Implementeaza API-ul JSON POST cu maximum 100 CUI/request si maximum 1 request/secunda, inclusiv reincer carile; trateaza erori, `found` si `notFound` fara a distruge informatii.
5. Implementeaza teste suplimentare offline. Pentru testele comune foloseste serverul HTTP local si fixture-urile fictive, **niciodata serviciul ANAF real**.
6. Ruleaza si repara testele; raporteaza separat testele care nu au putut fi rulate. Nu pretinde rezultate neverificate.
7. Documenteaza instalarea, folosirea CLI si limitarea derivata din lipsa unei coloane de status/verificare in DB.
8. Prezinta fisierele create sau modificate, rezultatele testelor, presupunerile, riscurile si sumarul `git diff`.

Restrictii: nu modifica `docs/SPEC.md`, `db/schema.sql`, `docs/TEST_PLAN.md`, `AGENTS.md` ori fixture-urile de baza. Nu accesa baze de date reale ale firmei sau fisiere externe proiectului. Nu executa `git push`, `git merge`, commit automat, instalari globale ori comenzi administrative. Nu examina implementarea celuilalt agent. Nu executa interogari live fara aprobarea expresa a utilizatorului.

Pentru Codex: lucreaza in folderul local deschis prin interfata grafica Windows. Pentru OpenCode: lucreaza numai in proiectul Ubuntu deja deschis din interfata OpenCode si foloseste modelul local configurat. **Promptul si criteriile de acceptanta raman identice** pe ambele platforme.
