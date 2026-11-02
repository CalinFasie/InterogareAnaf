# Instructiuni comune: Codex Windows si OpenCode Ubuntu

1. Citeste integral `docs/SPEC.md`, `docs/TEST_PLAN.md`, `db/schema.sql` si `README.md` inainte de modificari.
2. Lucreaza numai pe ramura atribuita (`codex-windows` sau `opencode-ubuntu`) si numai in directorul acestui repository.
3. Contractul comun, schema si testele de acceptanta sunt baza fixa pentru implementari; nu le modifica in timpul sarcinii unui singur agent. Testele suplimentare se pun in fisiere separate.
4. Implementeaza Python 3.11+ si CLI-ul comun; foloseste exclusiv SQLite pentru citirea CUI, salvarea celor noua campuri selectate si istoricul incercarilor.
5. Schema aplicativa are numai `parteneri` (exact 11 coloane) si `istoric_verificari`. Nu adauga alte tabele ori coloane, nici date ANAF necerute, JSON brut, metadate sau secrete.
6. Fiecare cerere efectiva jurnalizeaza un rand per CUI din lot. Pastreaza retries si istoricul append-only. Actualizarea ANAF si randul `GASIT` se comit in aceeasi tranzactie.
7. ANAF live nu se apeleaza din teste, la instalare sau automat. Testele pot folosi numai un server HTTP local simulat pe loopback.
8. Nu accesa baze de date reale ale firmei, alte repo-uri ori credentiale. Nu afisa date sensibile in loguri.
9. Nu executa `git push`, merge, commit automat, operatii administrative sau instalari globale fara instructiune explicita a utilizatorului.
10. Nu consulta codul ori rezultatele implementarii celuilalt agent. Foloseste acelasi contract, fixture-uri si teste comune.
11. Inchide explicit fiecare conexiune SQLite la finalul folosirii. Context managerul `sqlite3.Connection` gestioneaza tranzactii, dar nu inchide conexiunea.
12. La final prezinta fisierele schimbate, comenzile rulate, rezultate reale, limitarile, sumarul `git diff` si instructiuni de pornire.
