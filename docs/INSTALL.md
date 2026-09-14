# INFORAXIS — Complete Installation Guide (from zero to running)

> **Who is this for?** Someone who has never installed this application before —
> no programming knowledge required. If you can install a normal Windows program
> and open a web browser, you can do this.
>
> **Time needed:** about 30–45 minutes the first time (mostly downloads).
>
> **What you will end up with:** the INFORAXIS web application running on
> your own computer, opened in your browser at `http://127.0.0.1:5000`.

---

## 0. The big picture (read this first — 2 minutes)

The application has **3 parts** you need to understand:

| # | Part | Plain-English explanation | You install it… |
|---|------|---------------------------|-----------------|
| 1 | **Python** | A tool that runs the application (like a game engine runs a game). | Once, from python.org |
| 2 | **PostgreSQL** | The database — a program that safely stores everything the app finds in your files. | Once, from postgresql.org |
| 3 | **INFORAXIS** | This application itself — you download it and start it. | Once, then just use it |

After installing, your **daily routine** is simply:

1. Double-click **`start.bat`** → a black window opens (leave it open).
2. Open your browser at **http://127.0.0.1:5000** → use the app.
3. When done, press **CTRL+C** in the black window (or just close it).

That's it. Everything below is just the one-time setup to get there.

### Words you will see (mini-glossary)

- **Terminal / Command Prompt / PowerShell** — the black window where you type
  text commands. On Windows 10/11: press `Win + R`, type `powershell`, Enter.
- **Browser** — Chrome, Edge, or Firefox.
- **`localhost` / `127.0.0.1`** — means "this computer itself". The app runs on
  your PC and you open it like a website, but nothing leaves your computer.
- **Password for `postgres`** — during the PostgreSQL install you invent a
  password for the database's built-in `postgres` user. **Write it down** — you
  need it once more in Step 7.

---

## Quick Install — The Interactive Installer (Recommended)

The project includes an interactive installer that handles everything:

```bash
# After cloning/downloading the project:
cd file_analysis
python install.py
```

The installer will:
1. ✅ Check Python version and all dependencies
2. ✅ Verify PostgreSQL is installed and running
3. ✅ Guide you through every configuration value
4. ✅ Write `.env` and `config.json` with your settings
5. ✅ Create the database and run schema migrations
6. ✅ Set up directories and file permissions
7. ✅ Verify the complete installation

### Installer options

```bash
python install.py                    # Full interactive installation
python install.py --check            # Prerequisites check only
python install.py --configure        # Reconfigure an existing installation
python install.py --verify           # Post-install verification only
python install.py --env production   # Set environment non-interactively
python install.py --non-interactive  # Use defaults/env vars (CI/unattended)
```

The rest of this guide covers manual installation and detailed explanations.

---

## PART A — Windows installation, step by step

### Step 1 — Install Python

1. Go to **https://www.python.org/downloads/** and click the big yellow
   **"Download Python 3.11"** button (any 3.10–3.12 version works; 3.11 is ideal).
2. Run the downloaded file (`python-3.11.x.exe`).
3. ⚠️ **VERY IMPORTANT:** on the first installer screen, tick the checkbox
   **"Add python.exe to PATH"** at the bottom — then click **Install Now**.
   (If you forget this, nothing later will work. If you already installed
   Python without it, just run the installer again and choose *Modify*.)
4. When it says "Setup was successful", click **Close**.
5. **Check it worked:** press `Win + R`, type `powershell`, press Enter, then type:
   ```powershell
   python --version
   ```
   You should see something like `Python 3.11.9`. ✅ If you see an error, restart
   your computer and try again (the PATH change sometimes needs a restart).

### Step 2 — Install PostgreSQL (the database)

1. Go to **https://www.postgresql.org/download/windows/** and click
   **"Download the installer"** (from EnterpriseDB). Download the latest
   version (16 or newer), Windows x86-64.
2. Run the installer. Click **Next** through the screens with these choices:
   - **Installation Directory:** leave default (`C:\Program Files\PostgreSQL\16`) → Next.
   - **Components:** leave everything ticked (at minimum *PostgreSQL Server*) → Next.
   - **Data Directory:** leave default → Next.
   - **Password:** ⚠️ **invent a password for the `postgres` user and WRITE IT DOWN.**
     You will type it once more in Step 7. (Example: `FileAnalysis2026!` — pick
     your own.) → Next.
   - **Port:** leave **`5432`** → Next. (The app expects exactly this port.)
   - **Locale:** leave default → Next → **Finish**.
3. At the end it may offer "Stack Builder" — **untick it**, you don't need it.
4. **Check it worked:** press `Win + R`, type `services.msc`, press Enter.
   In the list, find **`postgresql-x64-16`** (number matches your version).
   Its *Status* should be **Running**. If not, right-click it → **Start**.
   (Right-click → Properties → Startup type **Automatic** keeps it always on.)

> 💡 **What did I just install?** A database *server* — a program that runs quietly
> in the background and stores data. You never open it directly; the INFORAXIS
> app talks to it automatically.

### Step 3 — Download the INFORAXIS application

**Option 1 — ZIP download (easiest, no extra tools):**

1. On the GitHub page of this project, click the green **`< > Code`** button →
   **Download ZIP**.
2. Open your `Downloads` folder, right-click the ZIP → **Extract All…**.
3. Move the extracted folder to a **short path without spaces**, for example:
   ```
   C:\fileanalysis
   ```
   ⚠️ Avoid folders like Desktop, OneDrive, or paths with spaces/accents —
   they cause mysterious failures. `C:\fileanalysis` is ideal. (Your current
   location `C:\Users\Solo\Videos\file_analysis` also works fine.)

**Option 2 — with Git (if you know Git):**

```powershell
git clone <repository-url> C:\fileanalysis
```

After this step, the folder (e.g. `C:\fileanalysis`) should contain files like
`run_web.py`, `requirements.txt`, `setup.bat`, `start.bat`, and this `INSTALL.md`.

### Step 4 — Run the one-click setup (once only)

1. Open the application folder (`C:\fileanalysis`) in File Explorer.
2. **Double-click `setup.bat`**.
   - Windows may show a blue "Windows protected your PC" warning (because the
     file came from the internet). Click **More info** → **Run anyway**.
3. A black window opens and does everything automatically:
   - creates an isolated Python environment (`.venv` — so the app never
     interferes with other Python programs),
   - downloads and installs all required packages (takes a few minutes,
     needs internet),
   - creates your personal `.env` settings file.
4. When you see **`Setup complete!`**, the window waits — press any key to close it.

> 🛠️ **What if I prefer typing commands?** The manual equivalent is:
> ```powershell
> cd C:\fileanalysis
> py -3 -m venv .venv
> .venv\Scripts\activate
> pip install -r requirements.txt
> copy .env.example .env
> ```

### Step 5 — (Optional but recommended) Put your database password in `.env`

The app can also get your database password from its setup page (Step 7), so
this step is optional — but doing it now removes scary-looking error messages
at the first start.

1. In the app folder, right-click the file **`.env`** → Open with → Notepad.
   (If you don't see `.env`, you skipped Step 4 — run `setup.bat` first.
   Note: `.env.example` is the template; `.env` is your personal copy.)
2. Find the line `DB_PASSWORD=` and add the postgres password from Step 2:
   ```
   DB_PASSWORD=FileAnalysis2026!
   ```
   (Use YOUR password. No quotes, no spaces around `=`.)
3. Save and close Notepad.

### Step 6 — Start the application

**Double-click `start.bat`** in the app folder. A black window opens and after
10–20 seconds you should see:

```
[OK] Starting web server on http://127.0.0.1:5000 (press CTRL+C to stop)
```

⚠️ **Leave this window open** while you use the app — closing it stops the app.
Minimizing is fine.

> 🛠️ Manual equivalent:
> ```powershell
> cd C:\fileanalysis
> .venv\Scripts\activate
> python run_web.py
> ```

### Step 7 — Complete the Database Setup page (once only)

1. Open your browser (Chrome/Edge/Firefox) and go to:
   ```
   http://127.0.0.1:5000
   ```
   On the very first visit you are automatically sent to the **Database Setup** page.
2. Enter **only the postgres password** from Step 2 (host, port, user and database
   name are pre-filled and standardized — don't change them).
3. Click **Setup / Initialize**.
4. Wait 10–60 seconds. The app now **automatically**:
   - creates the `analysis` database (if missing),
   - creates all tables (words, paths, contents, users, jobs, …),
   - marks the system as initialized.
5. You are redirected to the login page. ✅ Database setup is finished forever
   (this page never appears again).

### Step 8 — Log in for the first time

On first startup the app creates an **administrator account** automatically:

- **Username:** `admin`
- **Password:** the app generated a random one and saved it in a file:
  ```
  C:\Users\<YourName>\AppData\Local\file-analysis\runtime\initial_admin_password.txt
  ```
  Open that file with Notepad, copy the password, and log in.
  (Tip: paste this into File Explorer's address bar to jump there:
  `%LOCALAPPDATA%\file-analysis\runtime`)

After logging in, the app forces you to **change the password** — pick something
you remember. The temporary password file is then deleted automatically.

> 🔑 **Prefer choosing the admin password yourself?** Before the first start,
> open `.env` in Notepad and set:
> ```
> APP_ADMIN_USERNAME=admin
> APP_ADMIN_PASSWORD=choose-something-strong
> ```
> Then that password is used instead of a generated one.

### Step 9 — Verify everything works (recommended)

1. Keep the server running (Step 6 window open).
2. Open a **second** PowerShell window and run:
   ```powershell
   cd C:\fileanalysis
   .venv\Scripts\activate
   python verify_readiness.py
   ```
3. At the end you want to see:
   ```
   READINESS: READY
   ```
   If some checks fail, see [Troubleshooting](#part-e--troubleshooting)
   — most failures name the exact missing piece (usually the DB password).

### Step 10 — What to do next (using the app)

- **Analyze files:** open **Operations → Input / Ingestion** in the web interface.
  - The simplest way: **drag & drop files** into the upload area — no
    configuration needed.
  - To analyze whole folders on your disk (e.g. `D:\cases`), an administrator
    must first allow that folder: in `.env`, set e.g.
    ```
    INGESTION_ROOTS=D:\cases;E:\evidence
    ```
    (several folders separated by `;`), restart `start.bat`, then use the
    server-path option. This allowlist is a safety feature — the app can only
    read folders you explicitly permit.
- **Search & browse:** use **Search**, **Paths**, **Analytics** in the menu.
- **Import reference data:** **Operations → Import Center**.
- **Follow jobs:** **Operations → Jobs** shows live progress of long analyses
  (cancel / pause / resume supported).
- **Daily routine:** double-click `start.bat`, use the browser, press CTRL+C
  in the black window when finished.

🎉 **Done! The installation is complete.**

---

## PART B — macOS / Linux installation

The steps are the same; only the commands differ.

1. **Python 3.11+:**
   - Ubuntu/Debian: `sudo apt update && sudo apt install python3 python3-venv python3-pip`
   - macOS: `brew install python@3.11` (install [Homebrew](https://brew.sh) first)
   - Check: `python3 --version`
2. **PostgreSQL 14+:**
   - Ubuntu/Debian: `sudo apt install postgresql postgresql-contrib` then
     `sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'your-password';"`
   - macOS: `brew install postgresql@16 && brew services start postgresql@16`
   - Make sure it listens on port `5432` (default).
3. **Download & extract** the app, e.g. to `~/fileanalysis`.
4. **Setup (once):**
   ```bash
   cd ~/fileanalysis
   bash setup.sh
   ```
5. **Set the DB password** in `.env` (`nano .env` → `DB_PASSWORD=...`).
6. **Start:** `bash start.sh` → open `http://127.0.0.1:5000` → complete the
   Database Setup page → log in (initial password file:
   `~/.local/share/file-analysis/runtime/initial_admin_password.txt`).
7. **Verify:** `source .venv/bin/activate && python verify_readiness.py`.

---

## PART C — Configuration Reference

The application uses a layered configuration system with clear precedence:

### Configuration precedence (highest wins)

| Priority | Source | Description |
|----------|--------|-------------|
| 1 | **OS environment variables** | Always win — set in shell, Docker, or CI |
| 2 | **`.env` file** | Project-local, loaded at startup, git-ignored |
| 3 | **`config.json`** | Structured JSON config, git-ignored |
| 4 | **`config/{env}.json`** | Environment overlay (staging, production) |
| 5 | **`config.example.json`** | Project defaults, tracked in git |
| 6 | **Dataclass defaults** | Built into the source code |

### Configuration files

| File | Purpose | Git-tracked? |
|------|---------|:------------:|
| `.env.example` | Template for `.env` — all settings documented | ✅ Yes |
| `.env` | Your personal settings (secrets live here) | ❌ No |
| `config.example.json` | JSON config template with all defaults | ✅ Yes |
| `config.json` | Your JSON config (may contain credentials) | ❌ No |
| `config/development.json` | Development environment overlay | ✅ Yes |
| `config/staging.json` | Staging environment overlay | ✅ Yes |
| `config/production.json` | Production environment overlay | ✅ Yes |
| `data/settings.json` | Runtime settings (managed by the app) | ❌ No |

### `.env` file settings

| Setting | Example | Meaning |
|---------|---------|---------|
| `DB_HOST` | `localhost` | Database computer (same PC → localhost) |
| `DB_PORT` | `5432` | Database port (default — don't change) |
| `DB_NAME` | `analysis` | Database name (created automatically) |
| `DB_USER` | `postgres` | Database user (default — don't change) |
| `DB_PASSWORD` | `your-password` | ⚠️ **Must match the Step 2 password** |
| `APP_ADMIN_USERNAME` / `APP_ADMIN_PASSWORD` | `admin` / `…` | Optional: choose the first admin login yourself |
| `PASSWORD_MIN_LENGTH` | `12` | Minimum password length for all accounts |
| `INGESTION_ROOTS` | `D:\cases;E:\evidence` | Folders the app may read from disk (`;`-separated; empty = uploads only) |
| `APP_DATA_DIR` | `C:\fileanalysis\data` | Where uploads/logs/settings are stored (default: your user profile — usually fine) |
| `FLASK_SECRET_KEY` | *(long random text)* | Signs login sessions; auto-generated if empty |
| `FLASK_ENV` | `production` | Deployment environment: development, staging, production |
| `FLASK_DEBUG` | `false` | Debug mode — **must** be false in production |
| `FLASK_PORT` | `5000` | Change if port 5000 is already used on your PC |
| `FLASK_HOST` | `0.0.0.0` | Network binding address |
| `MAX_WORKERS` | `8` | Concurrent file processing workers |
| `FILE_PROCESSING_TIMEOUT` | `1200` | Per-file processing timeout (seconds) |
| `SECURITY_MAX_FAILED_LOGINS` | `5` | Account lockout after this many failures |
| `SECURITY_LOCKOUT_MINUTES` | `15` | Lockout duration |
| `SECURITY_SESSION_HOURS` | `12` | Session lifetime (hours) |
| `SECURITY_SESSION_IDLE_HOURS` | `6` | Idle session timeout (hours) |
| `RATE_LIMIT_PER_MINUTE` | `60` | API rate limit (requests/min/client) |
| `RATE_LIMIT_PER_HOUR` | `600` | API rate limit (requests/hour/client) |
| `LOG_LEVEL` | `INFO` | Logging verbosity: DEBUG, INFO, WARNING, ERROR |
| `DB_POOL_MIN_CONNECTIONS` | `2` | Minimum database connections |
| `DB_POOL_MAX_CONNECTIONS` | `25` | Maximum database connections |

After editing `.env`, **restart** the server (CTRL+C, then `start.bat` again).

### Environment-specific settings

The `config/` directory contains per-environment overlays. These are applied
on top of `config.json` based on the `FLASK_ENV` setting:

| Environment | Purpose | Debug | Rate Limit | Session |
|-------------|---------|:-----:|:----------:|:-------:|
| `development` | Local iteration | ✅ On | 300/min | 12h |
| `staging` | Pre-production testing | ❌ Off | 120/min | 12h |
| `production` | Live deployment (default) | ❌ Off | 30/min | 8h |

### Updating configuration after installation

You can modify settings without re-running the full installer:

1. **Quick change:** Edit `.env` → restart server.
2. **Structured change:** Edit `config.json` → restart server.
3. **Reconfigure interactively:** `python install.py --configure`
4. **Web UI:** Login as admin → Settings page (most runtime settings).
5. **Environment switch:** Change `FLASK_ENV` in `.env` → restart.

---

## PART D — Optional features (file formats)

The basic install reads TXT, HTML, E-mail, ZIP/7z/RAR archives and calendars.
For more formats, install these extras (with the virtual environment active):

```powershell
.venv\Scripts\activate
pip install "file-analysis[pdf]"        # PDF files (recommended)
pip install "file-analysis[office]"     # Word, Excel, PowerPoint
pip install "file-analysis[ocr]"        # text in scanned images (needs Tesseract installed separately)
pip install "file-analysis[ebook]"      # EPUB, MOBI e-books
pip install "file-analysis[audio]"      # audio metadata (MP3, FLAC, …)
pip install "file-analysis[media]"      # video files (large download)
```

Or everything at once: `pip install "file-analysis[pdf,office,ocr,ebook,audio]"`.
Restart the server afterwards.

---

## PART E — Troubleshooting

> **Rule #1:** after any fix, **restart the server** (CTRL+C in the black window,
> then double-click `start.bat` again) and **refresh the browser** (CTRL+F5).

### E1. `fe_sendauth: no password supplied` / `Failed to initialize connection pool`

**This is the error from the report that motivated this guide.** It means:
the app tried to reach PostgreSQL but has no password yet.

- **It's expected BEFORE you complete Step 7** (the Database Setup page) or
  Step 5 (`.env` password) — and it disappears by itself afterwards.
- **Fix (pick one):**
  1. *Easiest:* open `http://127.0.0.1:5000/setup` in the browser, enter the
     postgres password from Step 2, click Setup. Done.
  2. *Alternative:* put the password in `.env` (`DB_PASSWORD=...`, see Step 5)
     and restart the server.
  3. *Interactive:* run `python install.py --configure` to reconfigure.
- If the message **persists after setup**, the password is wrong: check
  Step 2's password, or change it (Windows: open **pgAdmin** → Servers →
  PostgreSQL → Login/Group Roles → postgres → Definition → new password →
  Save; then re-enter it in `.env` / the Settings page).

### E2. `python run_web.py` prints lines and returns to the prompt (no server)

Fixed in this version (`run_web.py` now starts the server and prints
`Starting web server on http://127.0.0.1:5000`). If you see the old behavior,
update to the latest code and use **`start.bat`**.

### E3. `python` is not recognized / `py` not found

Python isn't installed or not on PATH. Re-run the Python installer → **Modify** →
tick **"Add python.exe to PATH"** → restart the computer → retry.

### E4. `pip install` fails (red errors)

- No internet? Connect and retry.
- Corporate proxy/antivirus blocking? Try a private network, or ask IT to allow
  `pypi.org` and `files.pythonhosted.org`.
- Very old `pip`? Run `python -m pip install --upgrade pip` first.
- Then re-run `setup.bat` (it's safe to run twice — it skips finished steps).

### E5. Browser shows "Can't reach this site" / connection refused

- Is the black server window still open with `Starting web server...`? If not,
  double-click `start.bat` again.
- Correct address? Use exactly `http://127.0.0.1:5000` (not `https`, no typo).
- Port conflict? If another program uses port 5000, set `FLASK_PORT=5001` in
  `.env`, restart, and open `http://127.0.0.1:5001`.

### E6. `connection to server at "localhost", port 5432 failed: Connection refused`

PostgreSQL isn't running. Windows: `Win+R` → `services.msc` → find
`postgresql-x64-…` → right-click → **Start**. Then restart `start.bat`.

### E7. Setup page says "Database is already initialized" but login fails

The database exists but the admin account is missing (interrupted first run).
Reset the admin account — see [E11](#e11-i-forgot-the-admin-password).

### E8. Login page loops / "Invalid username or password"

- First login ever? Use the generated password file (Step 8), not your
  postgres password — these are two different passwords!
- `Caps Lock` on? Usernames are case-sensitive.
- Account locked after 5 wrong tries? Wait 15 minutes, then retry.

### E9. I don't remember the postgres password (Step 2)

Windows: open **pgAdmin 4** (installed with PostgreSQL) → Servers →
PostgreSQL 16 → **Login/Group Roles** → right-click **postgres** →
Properties → **Definition** tab → set a new password → Save.
Then update `.env` (`DB_PASSWORD=...`) and restart the server, or update it on
the app's **Settings** page.

### E10. How do I start over with an empty database?

⚠️ This **deletes all analyzed data**. Steps:

1. Stop the server (CTRL+C).
2. Open **pgAdmin** → Databases → right-click `analysis` → Delete/Drop.
3. Delete the marker files: `.system_initialized` and `.db_config.json` in the
   app folder, and the settings store under
   `%LOCALAPPDATA%\file-analysis\config` (Windows).
4. Start the server → the Database Setup page (Step 7) appears again.

### E11. I forgot the admin password

With access to the computer you can always recover:

1. Stop the server.
2. In `.env`, set a new `APP_ADMIN_PASSWORD=...` (temporary).
3. Delete the users so bootstrap recreates the admin — easiest via pgAdmin:
   open database `analysis` → Query Tool → run:
   ```sql
   DELETE FROM sessions;
   DELETE FROM users;
   ```
4. Start the server → the admin is recreated with your temporary password →
   log in → change it on the profile page → **remove `APP_ADMIN_PASSWORD`
   from `.env`** and restart.

### E12. The black window shows lots of WARNING/ERROR lines at startup

Before Step 7 is completed, database-related ERROR lines are **normal** — the
app is retrying until you enter the password in the setup page. After a
successful setup + restart, startup should be mostly `✅` / `[OK]` lines.
Anything else: read the message, find it in this guide, or check
`%LOCALAPPDATA%\file-analysis\logs` for details.

### E13. Antivirus / firewall popups

- The Python/PostgreSQL installers and the local web server (port 5000) may
  trigger SmartScreen or firewall prompts. Allow **private networks** access.
  The app only needs *local* access — never expose port 5000 to the internet
  unless you know what you're doing (see `docs/SECURITY.md`).

### E14. CSRF token is missing or invalid (setup page)

If the setup page returns "CSRF token is missing or invalid", ensure you are
running the latest version of the code. This was a known issue in earlier
versions where the setup page template did not include the CSRF token. Update
to the latest code, hard-refresh the browser (CTRL+F5), and retry.

---

## PART F — Uninstall / moving the app

- **Stop using it:** press CTRL+C in the server window. Nothing runs in the
  background except PostgreSQL (which you can leave installed).
- **Remove the app:** delete the app folder (e.g. `C:\fileanalysis`) and, if
  wanted, the data folder `%LOCALAPPDATA%\file-analysis`.
- **Remove everything:** additionally uninstall *Python* and *PostgreSQL* via
  Windows Settings → Apps.
- **Move to another computer:** install Python + PostgreSQL there, copy the app
  folder, run `setup.bat`, and either re-run the setup wizard (fresh database)
  or restore a backup (`pg_dump` — see `docs/DATABASE.md`).

---

## Quick-reference card (print me)

```
FIRST TIME ONLY:
  1. Install Python 3.11   (tick "Add python.exe to PATH")
  2. Install PostgreSQL     (remember the postgres password, port 5432)
  3. Extract the app to C:\fileanalysis
  4. Double-click setup.bat          (or: python install.py)
  5. Double-click start.bat
  6. Browser → http://127.0.0.1:5000 → enter postgres password
  7. Log in as admin (password in %LOCALAPPDATA%\file-analysis\runtime\)

EVERY DAY:
  1. Double-click start.bat (leave the black window open)
  2. Browser → http://127.0.0.1:5000
  3. CTRL+C in the black window when finished

RECONFIGURE:
  python install.py --configure
```

Further reading for advanced topics: `docs/` folder —
`windows.md`, `DEPLOYMENT.md`, `DATABASE.md`, `SECURITY.md`, `operations.md`.
