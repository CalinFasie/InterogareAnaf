# Instructiuni comune: Codex Windows si OpenCode Ubuntu

1. Citeste integral `docs/SPEC.md`, `docs/TEST_PLAN.md`, `db/schema.sql` si `README.md` inainte de modificari.
2. Lucreaza numai pe ramura atribuita (`codex-windows` sau `opencode-ubuntu`) si numai in directorul acestui repository.
3. Nu modifica specificatia comuna, schema, fixture-urile sau testele de acceptanta. Cere clarificare doar daca blocajul este real; altfel documenteaza presupunerile.
4. Implementeaza Python 3.11+ si CLI-ul comun; foloseste exclusiv SQLite pentru citirea CUI si salvarea rezultatelor ANAF.
5. Nu adauga alte coloane sau tabele. Nu calcula/stoca statut TVA, RO e-Factura, inactive, metadate sau JSON brut.
6. ANAF live nu se apeleaza din teste, la instalare sau automat. Testele pot folosi doar un server local simulat.
7. Nu accesa fisiere reale ale companiei, alte repo-uri sau credentiale. Nu afisa date sensibile in loguri.
8. Nu executa `git push`, `git merge`, commit automat, operatii administrative sau instalari globale.
9. Nu consulta codul ori rezultatele implementarii celuilalt agent. Foloseste aceleasi fixture-uri si aceleasi teste de contract.
10. La final prezinta: fisierele schimbate, comenzile rulate, rezultate reale ale testelor, limitari, `git diff` si instructiuni de pornire.
