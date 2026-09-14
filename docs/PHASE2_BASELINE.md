# Phase 2 — Baseline Freeze and Workstream Record

## §1 Baseline (frozen before any Phase 2 change)

Verified independently, not assumed:

| Item | Value | How verified |
|---|---|---|
| Branch | `arena/01a090de-file-analysis` | `git rev-parse --abbrev-ref HEAD` |
| Local HEAD | `66cb6869f3669fb390fe3915cb960974f86b2992` | `git rev-parse HEAD` |
| Remote branch | `66cb6869f3669fb390fe3915cb960974f86b2992` | `git ls-remote origin refs/heads/arena/01a090de-file-analysis` |
| Working tree | clean | `git status --short` → empty |
| Commits since base `0afc8be` | 6 | `git log --oneline 0afc8be..HEAD` |

The six baseline commits, unchanged and not squashed:

```
66cb686 docs: source-first audit of the core data pipeline
4b7c1ca fix(SEARCH-01): full-text search returned zero results for every query
e67b38d fix(HASH-01): never fabricate a content identity from path and mtime
ed18180 fix(ROUTE-01): resolve reader conflicts explicitly; CSV gets real structure
1a5757f fix(PDF-01/02): never discard a PDF page's own text layer
10097f9 fix(DETECT-01): identify files by content, not by extension alone
```

### Baseline test results at `66cb686`

```
tests/              295 passed, 7 failed, 1 skipped, 41 errors
tests/unit          231 passed
tests/integration    47 passed, 1 skipped, 3 errors
tests/security        7 failed, 16 passed, 24 errors
tests/e2e             1 passed, 14 errors
```

**Every one of the 7 failures and 41 errors has a single environmental root
cause**, verified rather than assumed: `/auth/login` returns `302 → /setup` in
this sandbox, so the `admin_client` fixture in `tests/conftest.py` fails and
`test_login_brute_force_rate_limited` observes `expected a 429 among [302, …]`.
All three integration errors are `test_cli_parity.py` frontend tests using the
same fixture.

**All data-pipeline suites are green.** These numbers are the regression
reference for Phase 2: no change may reduce `295 passed` or increase the
failure/error counts.

### Database

**There is no production database in this environment.** Verified: no system
`postgres`/`psql`/`pg_ctl` on PATH, no Postgres port listening, no `DB_*`
environment variables set. Every database used by the test suite is a
disposable `pgserver` instance created in a temporary directory per session and
discarded afterwards.

The §18 constraint against destructive database operations is therefore
satisfied trivially here — but it is recorded explicitly so that no Phase 2
change is ever written on the assumption that a throwaway database is
acceptable in production.

### Environment

`.venv` does **not** persist between turns in this sandbox and must be
recreated. Debian apt repositories are unreachable (HTTP blocked), so system
packages such as the `tesseract` binary **cannot** be installed. PyPI and
github.com are reachable. This constraint shaped the OCR engine choice below.
