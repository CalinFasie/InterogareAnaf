# InterogareAnaf

Proiect Python pentru a interoga API-ul ANAF TVA v9 pentru aproximativ 4.000 de CUI-uri, citite din SQLite. Se stocheaza exclusiv denumirea ANAF, `nrRegCom` si sapte campuri din `adresa_sediu_social`. Sunt pastrate separat denumirea initiala si cea din ANAF.

## Stare

Acesta este **baseline-ul comun de specificatie**, nu o aplicatie implementata. Nu contine o baza de date de productie si nu efectueaza interogari ANAF. Agentii de dezvoltare vor construi aplicatia independent pe ramurile `codex-windows` si `opencode-ubuntu`.

## Documente

- `docs/SPEC.md` — contract functional si tehnic, inclusiv comportamentul la erori.
- `db/schema.sql` — schema SQLite cu exact 11 coloane.
- `docs/SETUP.md` — pornirea de la zero, Windows/Codex GUI, Ubuntu/OpenCode, Git/GitHub.
- `docs/TEST_PLAN.md` — criterii comune de acceptanta.
- `prompts/IMPLEMENTARE.md` — acelasi prompt pentru ambii agenti.
- `AGENTS.md` — instructiuni comune pentru agenti.
- `fixtures/anaf_sintetic.json` — simulare fara date reale.
- `fixtures/parteneri_sintetici.csv` — exemplu de incarcare initiala.
- `tests/test_contract.py` — teste comune offline, de rulat dupa implementare.

## Comenzi pe care agentii trebuie sa le implementeze

```bash
python -m interogare_anaf init-db --db data/private/parteneri.sqlite3
python -m interogare_anaf import-cui --db data/private/parteneri.sqlite3 --input data/private/parteneri.csv
python -m interogare_anaf run --db data/private/parteneri.sqlite3 --date 2026-10-28
python -m interogare_anaf run --db data/private/parteneri.sqlite3 --date 2026-10-28 --only-missing
```

`import-cui` este doar pentru popularea initiala a bazei; la interogare sursa si destinatia sunt exclusiv SQLite. **Nu rula `run` pe date reale in timpul dezvoltarii.**

## Referinta oficiala ANAF

- Endpoint v9: https://webservicesp.anaf.ro/api/PlatitorTvaRest/v9/tva
- Documentatie v9: https://static.anaf.ro/static/10/Anaf/Informatii_R/Servicii_web/doc_WS_V9.txt
- Pagina oficiala: https://static.anaf.ro/static/10/Anaf/Informatii_R/Servicii_web/servicii_sincron.html
