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
| Long paths | The app does not opt in itself: a stored path over `OPERATIONS_MAX_STAGED_PATH_CHARS` (240 here) is refused for that file with its length and the limit, and whether longer paths work at all depends on the machine's `LongPathsEnabled` setting |
| Console | UTF-8 with `errors="replace"` on win32 (all entry points) |
| Production WSGI | waitress (pure Python); gunicorn is not available on Windows |

## Verify the three inputs before accepting a build

The engine's three ways in - one file, a whole folder, and a path on the
server - are checked by a script that runs *on this machine*, using the same
application code and the same endpoints the browser calls:

```bat
.venv\Scripts\python.exe scripts\verify_windows_ingestion.py --username admin
```

It prompts for the password, signs in, and prints `PASS` / `FAIL` / `SKIP` per
check, with the platform, the data root, the parsed `INGESTION_ROOTS` and the
Windows long-path setting at the top so the result can be read in context:

* one file chosen on its own (content and checksum verified on disk),
* a whole folder, exactly as the browser reports it - forward slashes,
  backslashes and a drive-qualified path - with the folder tree verified on the
  real filesystem,
* names Windows refuses (`CON`, `NUL`, `aux`, trailing dots, `: * ? " < > |`)
  staged and *read back*, which only the real filesystem can answer,
* the staged-path length limit, on both sides of it,
* a typed server path (dry run, nothing is read), the separator/case variants a
  Windows operator types, and the refusals for outside-root and traversal,
* a large file staged in chunks, with the assembled file's checksum verified,
* the retired surfaces: `/upload` -> 302 `/operations/input`,
  `POST /upload/process-path` -> 404, and all three controls present on the page.

Add `--server-path "C:\Case 2026-014\Evidence"` to dry-run a folder of your own
inside a configured root, and `--json` for machine-readable output. Nothing is
ingested and the staged files it creates are removed again before it exits; the
exit code is 0 only when nothing failed.
