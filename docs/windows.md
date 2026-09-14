# Windows-native operation guide

The application runs **primarily on native Windows**. Drive-qualified paths
(`C:\data\evidence`), UNC network shares (`\\server\share\cases`), and
backslash separators are first-class everywhere: ingestion roots, server-path
validation, upload staging, checkpoints, and extracted-file paths.

## Prerequisites

* Windows 10/11 or Windows Server 2016+
* Python 3.10+ from python.org ("Add python.exe to PATH" during install)
* PostgreSQL 14+ for Windows (or Docker Desktop)
* Optional: `waitress` for production serving (pure-Python WSGI; gunicorn is
  POSIX-only)

## Setup

```bat
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install waitress          :: optional, production WSGI server
copy .env.example .env
```

## Configuration (.env) — Windows paths

```bat
DB_HOST=localhost
DB_PORT=5432
DB_NAME=analysis
DB_USER=postgres
DB_PASSWORD=your-password

# Native Windows paths, semicolon-separated. UNC shares work too.
INGESTION_ROOTS=C:\data\evidence;D:\inbox;\\fileserver\cases

# Data root (uploads, exports, runtime keys). Default is per-user:
#   %LOCALAPPDATA%\file-analysis
APP_DATA_DIR=C:\fileanalysis\data

FLASK_SECRET_KEY=<generate-a-long-random-string>
```

Notes:

* `INGESTION_ROOTS` uses `;` as the separator — the one separator that is
  legal inside Windows paths.
* Paths validate case-insensitively and accept `/` or `\` separators
  (`C:/data` == `C:\data`).
* Relative ingestion candidates resolve against the configured roots, never
  against the working directory.
* If no roots are configured, server-path ingestion is disabled (uploads
  still work); the Input page shows this state via `/api/input/options-info`.
* Long-path limit: enable once for corpora with deep trees
  (`LongPathsEnabled=1` in
  `HKLM\SYSTEM\CurrentControlSet\Control\FileSystem`). The reader also
  applies the `\\?\` extended prefix automatically for paths > 260 chars.

## Initialize and run

```bat
python init_admin.py          :: first admin user (see README)
python verify_readiness.py    :: 25/25 readiness checks
python run_web.py             :: development server on 0.0.0.0:5000
```

Production serving on Windows (no gunicorn):

```bat
waitress-serve --host=0.0.0.0 --port=5000 apps.web.app:app
```

Set `FLASK_HOST` / `FLASK_PORT` to change the development server binding.
`FLASK_DEBUG=true` requires `FLASK_ENV=development` (production startup
refuses debug mode).

## CLI adapters on Windows

```bat
python run_cli.py --path C:\data\evidence\case42 --source src --side a --workers 4
python run_import.py --data-file domains.xlsx
```

Console output is forced to UTF-8 (with replacement) on Windows, so emoji
progress output survives redirected/service consoles.

## Running as a service

The codebase spawns no processes that need console handles; job workers are
threads. Any service wrapper works, e.g. NSSM:

```bat
nssm install FileAnalysis "C:\fileanalysis\.venv\Scripts\python.exe" "C:\fileanalysis\run_web.py"
nssm set FileAnalysis AppDirectory C:\fileanalysis
nssm start FileAnalysis
```

## Windows-specific behaviors

| Area | Behavior |
| --- | --- |
| Ingestion roots | `;`-separated; drive letters and UNC allowed under the allowlist |
| Path validation | Case-insensitive, separator-tolerant containment (`core/path_safety.py`) |
| Upload staging | `%LOCALAPPDATA%\file-analysis\uploads\<id>\` by default |
| Data root | `%LOCALAPPDATA%\file-analysis` unless `APP_DATA_DIR` set |
| Long paths | `\\?\` prefix applied automatically above 260 chars |
| Console | UTF-8 with `errors="replace"` on win32 (all entry points) |
| Production WSGI | waitress (pure Python); gunicorn is not available on Windows |
