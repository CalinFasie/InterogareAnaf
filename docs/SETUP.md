# Pornire de la zero — InterogareAnaf / Windows + Ubuntu

## 0. Ce este deja stabilit si ce nu presupunem

- Repo-ul GitHub: `InterogareAnaf` (in documentatia anterioara: `https://github.com/CalinFasie/InterogareAnaf`). Verifica existenta, accesul si ramura curenta inainte de operatii; acest pachet nu a modificat GitHub.
- Windows: directorul `D:\Github\InterogareAnaf` este cel declarat in conversatia initiala. Verifica daca exista si daca are modificari locale necomise.
- Ubuntu: **nu exista inca directorul aplicatiei**. Nu presupunem ca exista vreo clonare sau DB.
- Din configuratia mentionata anterior, OpenCode ar rula ca `code-agent`, cu HOME `/var/lib/code-agent` si interfata Web accesibila posibil prin tunel la `https://localhost:19444`. Verifica aceste conditii in loc sa le presupui.
- Codex pe Windows se deschide in **interfata grafica**; nu sunt necesare comenzi de pornire `codex` in terminal.
- Ai descarcat pachetul baseline din aceasta conversatie. Copiaza **continutul** folderului `InterogareAnaf-baseline` in repository, nu folderul propriu-zis.

## 1. Windows: pregatirea baseline-ului comun pe `main`

Deschide PowerShell obisnuit, nu este nevoie de administrator:

```powershell
Set-Location 'D:\Github\InterogareAnaf'
git status -sb
git remote -v
git fetch origin
git switch main
git pull --ff-only
```

**Opreste-te daca `git status` arata modificari neasteptate sau daca `git pull --ff-only` esueaza.** Nu forta o rescriere sau resetare a istoricului.

Dezarhiveaza pachetul furnizat si copiaza in `D:\Github\InterogareAnaf` fisierele/directoarele: `README.md`, `.gitignore`, `AGENTS.md`, `db`, `docs`, `fixtures`, `prompts`, `tests`. Compara manual `README.md` existent inainte de suprascriere.

Verifica baza comuna si fa commit/push numai dupa inspectie:

```powershell
git status --short
git diff --stat
git add README.md .gitignore AGENTS.md db docs fixtures prompts tests
git diff --cached --stat
git commit -m "spec: baseline SQLite pentru comparatia agentilor"
git push origin main
git rev-parse HEAD
```

Noteaza hash-ul afisat: trebuie sa fie acelasi punct de plecare pentru Codex si OpenCode.

Creeaza ramurile **doar daca nu exista deja**. Daca exista, verifica istoricul si adapteaza comenzile; nu folosi `-f`:

```powershell
git switch -c codex-windows
git push -u origin codex-windows

git switch main
git branch opencode-ubuntu main
git push origin opencode-ubuntu

git switch codex-windows
git status -sb
```

Ultima comanda trebuie sa indice `## codex-windows` si un arbore de lucru curat.

Creeaza mediul Python pentru lucru local (dupa ce Python este verificat):

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe --version
```

## 2. Windows: Codex prin interfata grafica

1. Deschide aplicatia **Codex** (GUI). Autentifica-te daca ti se cere.
2. Foloseste optiunea de adaugare/deschidere proiect/folder si selecteaza `D:\Github\InterogareAnaf`.
3. Verifica in aplicatie ca proiectul foloseste directorul local si ramura `codex-windows`. Daca interfata ofera mod `worktree`, nu confunda un worktree separat cu directorul pe care ai pregatit ramura.
4. Porneste o conversatie/sarcina noua si copiaza integral textul din `prompts/IMPLEMENTARE.md`.
5. Permite editari/teste strict in repository, dar nu aproba accesul la alte directoare, credentiale, modificari administrative ori apeluri ANAF live.
6. La final, inspecteaza modificarile in GUI si verifica rezultatele testelor. **Nu accepta automat** orice operatiune Git cu efect extern.

Nu executa `codex --sandbox ...` — acea comanda era pentru CLI si nu corespunde modului de utilizare ales acum.

## 3. Ubuntu: creare proiect de la zero, fara chei GitHub in agent

### 3.1. Windows: exporta baseline-ul din `main`

Prin PowerShell, din acelasi repository:

```powershell
Set-Location 'D:\Github\InterogareAnaf'
git switch main
git bundle create "$env:TEMP\InterogareAnaf-baseline.bundle" main
scp "$env:TEMP\InterogareAnaf-baseline.bundle" hp-files:~/InterogareAnaf-baseline.bundle
git switch codex-windows
```

`hp-files` este aliasul SSH mentionat in procedura precedenta. Daca nu functioneaza, foloseste hostul SSH real, fara sa inventezi o conexiune. Pe Ubuntu, fisierul trebuie identificat in HOME-ul utilizatorului SSH (in exemplul anterior: `/home/test/`).

### 3.2. Ubuntu: verifica mediul existent

Conecteaza-te prin SSH cu un cont ce are drepturile administrative necesare si verifica:

```bash
whoami
id code-agent
getent passwd code-agent
command -v git
command -v python3
python3 --version
ls -l ~/InterogareAnaf-baseline.bundle
```

Daca `code-agent` nu exista, nu executa comenzile `sudo -u code-agent` pana cand nu este clarificata configuratia OpenCode. Nu cream ori schimbam conturi de serviciu automat.

### 3.3. Ubuntu: crearea directoarelor si clonarea din bundle

**Doar daca** utilizatorul de serviciu este `code-agent`, home-ul este `/var/lib/code-agent`, iar bundle-ul a ajuns in `/home/test/InterogareAnaf-baseline.bundle`:

```bash
sudo install -d -o code-agent -g code-agent -m 0700 \
  /var/lib/code-agent/workspace \
  /var/lib/code-agent/tmp

sudo install -o code-agent -g code-agent -m 0600 \
  /home/test/InterogareAnaf-baseline.bundle \
  /var/lib/code-agent/tmp/baseline.bundle

sudo -u code-agent -H env HOME=/var/lib/code-agent \
  git clone -b main \
  /var/lib/code-agent/tmp/baseline.bundle \
  /var/lib/code-agent/workspace/InterogareAnaf

sudo -u code-agent -H env HOME=/var/lib/code-agent \
  git -C /var/lib/code-agent/workspace/InterogareAnaf \
  remote remove origin

sudo -u code-agent -H env HOME=/var/lib/code-agent \
  git -C /var/lib/code-agent/workspace/InterogareAnaf \
  switch -c opencode-ubuntu

sudo -u code-agent -H env HOME=/var/lib/code-agent \
  git -C /var/lib/code-agent/workspace/InterogareAnaf \
  status -sb
```

Rezultatul trebuie sa indice `## opencode-ubuntu`. Prin eliminarea remote-ului temporar, agentul nu primeste un remote GitHub autenticat si nu poate face push acolo din aceasta clona.

Creeaza un mediu virtual Python **sub proprietarul proiectului**:

```bash
sudo -u code-agent -H env HOME=/var/lib/code-agent \
  python3 -m venv /var/lib/code-agent/workspace/InterogareAnaf/.venv

sudo -u code-agent -H env HOME=/var/lib/code-agent \
  /var/lib/code-agent/workspace/InterogareAnaf/.venv/bin/python --version
```

Daca `python3 -m venv` lipseste, verifica pachetul `python3-venv` potrivit distributiei inainte de a aproba instalarea, fara sa presupui versiunea Ubuntu.

**Nu este necesar sa creezi manual DB acum.** Ambele implementari vor oferi comanda `init-db`, care aplica schema identica.

### 3.4. Ubuntu: OpenCode Web si inferenta locala

- Daca OpenCode Web si tunelul SSH mentionat anterior sunt deja functionale, deschide din Windows `https://localhost:19444`. Daca nu sunt, nu considera URL-ul functional fara verificare.
- Deschide/adauga proiectul `/var/lib/code-agent/workspace/InterogareAnaf`.
- Selecteaza modelul Ollama local disponibil; in setup-ul anterior acesta era `ollama/qwen38-abl-64k:latest`. Verifica numele efectiv disponibil in interfata OpenCode/Ollama.
- Foloseste **acelasi** text din `prompts/IMPLEMENTARE.md` si acelasi set de teste.
- Nu aproba acces la chei SSH, credentiale, alte proiecte sau directoare personale. Nu porni apeluri ANAF reale in timpul implementarii.

## 4. Dupa implementare: creeaza DB si incarca CUI-urile

Comenzile de mai jos sunt de rulat **doar dupa ce agentul implementeaza si testeaza CLI-ul**. Exemplu cu Python din mediul virtual Windows:

```powershell
.\.venv\Scripts\python.exe -m interogare_anaf init-db --db data/private/parteneri.sqlite3
.\.venv\Scripts\python.exe -m interogare_anaf import-cui --db data/private/parteneri.sqlite3 --input data/private/parteneri.csv
```

Fisierul local `data/private/parteneri.csv` (ignorat de Git) este destinat **doar incarcarii initiale**, cu antet `cui;denumire_initiala`, UTF-8 si CUI numerice. Daca datele sunt deja in alta baza SQLite, adaptam metoda de incarcare, fara a schimba schema.

Verificare **offline** cu teste comune:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Rulare ANAF reala numai la decizia utilizatorului, dupa backup si validare:

```powershell
.\.venv\Scripts\python.exe -m interogare_anaf run --db data/private/parteneri.sqlite3 --date 2026-10-28
```

Data afisata este un exemplu: pentru o interogare ulterioara alege data dorita. Nu promitem rezultate sau timp de raspuns fix.

Pe Ubuntu utilizeaza aceleasi subcomenzi cu `.venv/bin/python`, in directorul proiectului, pe o **baza de date separata**, pentru a evita modificarea datelor de productie si interferenta comparatiei.

## 5. Publicarea implementarii OpenCode in GitHub dupa revizuire

Dupa dezvoltare, verifica modificarile Ubuntu si efectueaza commit local **manual**, ca utilizator `code-agent`:

```bash
sudo -u code-agent -H env HOME=/var/lib/code-agent \
  git -C /var/lib/code-agent/workspace/InterogareAnaf status -sb
```

Nu adauga baze `.sqlite3`, CSV real, `.env` sau date ANAF. Dupa revizuire si commit local:

```bash
sudo -u code-agent -H env HOME=/var/lib/code-agent \
  git -C /var/lib/code-agent/workspace/InterogareAnaf \
  bundle create /var/lib/code-agent/tmp/opencode-final.bundle opencode-ubuntu

sudo install -o test -g test -m 0600 \
  /var/lib/code-agent/tmp/opencode-final.bundle \
  /home/test/opencode-final.bundle
```

Numele `test` si calea `/home/test` sunt valabile **numai daca** sunt utilizatorul/locatia SSH confirmate anterior.

Pe Windows, dupa ce ai revizuit istoria locala:

```powershell
scp hp-files:~/opencode-final.bundle "$env:TEMP\opencode-final.bundle"
Set-Location 'D:\Github\InterogareAnaf'
git fetch "$env:TEMP\opencode-final.bundle" refs/heads/opencode-ubuntu:refs/heads/opencode-ubuntu
git push origin opencode-ubuntu
```

Daca apare `non-fast-forward` ori alta neconcordanta, opreste procedura si investigheaza; nu folosi `--force`. Ramura `codex-windows` se comite si se publica separat, manual, dupa revizuire.

## 6. Comparatia agentilor

Ambele variante trebuie sa inceapa cu acelasi hash `main`, sa foloseasca acelasi prompt si testele comune. Se compara: acuratetea maparii, respectarea schemei, testele automate offline, robustete la erori, lizibilitate, numar de interventii umane, utilizarea resurselor si diferentele de confidentialitate/cost. Nu se compara viteza ANAF din doua momente de retea diferite drept performanta a agentului. Nu se face merge in `main` inaintea evaluarii.
