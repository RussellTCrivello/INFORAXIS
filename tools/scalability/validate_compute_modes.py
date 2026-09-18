#!/usr/bin/env python3
"""Prove that compute-device selection changes performance only.

The requirement is absolute: choosing CPU, GPU, CPU+GPU or automatic mode must
never alter forensic accuracy, extracted content, hashes, metadata, indexing
results or stored evidence. This script establishes that by *executing* the same
corpus under each mode and comparing the resulting evidence fingerprint of every
stored object:

  * file hash (SHA-256 of the bytes as read by the store path),
  * file status and file type,
  * the raw extracted text and its character count (``contents_raw``),
  * the indexed word multiset (digest over words sorted by value) and its size,
  * the number of persisted title rows,
  * the per-file row counts in ``contents``/``contents_raw``/``words_paths``.

Not compared, deliberately: ``contents.content_data``.  Measured while building
this validator, that blob is a compressed word-position index keyed by the
database-assigned ``words.id``.  Word ids come from concurrent inserts, so the
same evidence compresses to different bytes on different runs - comparing it
would report a difference between *any* two runs, including two runs of the same
mode.  The id-free word multiset digest below is the evidence contract that must
hold; the raw extracted text is compared directly.

Any difference is reported per file and the run fails.

Modes exercised:

    gateway            : process-wide gateway, requested mode (default AUTO)
    cpu                : COMPUTE_MODE=cpu
    gpu                : COMPUTE_MODE=gpu  (expected: graceful CPU fallback)
    cpu+gpu            : COMPUTE_MODE=cpu+gpu
    bypass             : COMPUTE_GATEWAY=0 (the layer switched off entirely)

The bypass run is the reference: whatever the gateway does, it must not change
what the pipeline stores relative to running without the layer at all.

Usage:
    validate_compute_modes.py [--corpus DIR] [--workdir DIR] [--files N]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

MODES = (
    ("cpu", {"COMPUTE_MODE": "cpu"}),
    ("auto", {"COMPUTE_MODE": "auto"}),
    ("gpu", {"COMPUTE_MODE": "gpu"}),
    ("cpu+gpu", {"COMPUTE_MODE": "cpu+gpu"}),
    ("bypass", {"COMPUTE_GATEWAY": "0"}),
)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--files", type=int, default=400)
    args = ap.parse_args(argv)

    workdir = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="compute_modes_"))
    workdir.mkdir(parents=True, exist_ok=True)

    corpus = Path(args.corpus) if args.corpus else workdir / "corpus"
    if not corpus.exists():
        subprocess.run([sys.executable, str(HERE / "gen_corpus.py"), str(corpus),
                        "--files", str(args.files), "--dirs-per-level", "3",
                        "--depth", "3", "--avg-bytes", "4096",
                        "--formats", "text,json,csv,binary,zip,pdf",
                        "--large-count", "3", "--large-bytes", "524288",
                        "--seed", "31337"], check=True, timeout=1800)

    results = {}
    for name, env in MODES:
        pgdata = workdir / f"pg_{name.replace('+', '_')}"
        fingerprints = _fingerprint_with_env(corpus, pgdata, env)
        results[name] = fingerprints
        print(f"{name:>8}: {len(fingerprints)} stored objects fingerprinted",
              flush=True)

    reference_name = "bypass"
    reference = results[reference_name]
    failures = []
    for name, fingerprints in results.items():
        if name == reference_name:
            continue
        missing = sorted(set(reference) - set(fingerprints))
        extra = sorted(set(fingerprints) - set(reference))
        differing = sorted(
            path for path in set(reference) & set(fingerprints)
            if reference[path] != fingerprints[path]
        )
        if missing or extra or differing:
            failures.append({
                "mode": name, "missing": missing[:10], "extra": extra[:10],
                "differing": differing[:10],
            })
        print(f"{name:>8}: missing={len(missing)} extra={len(extra)} "
              f"differing={len(differing)}", flush=True)

    report = {
        "corpus": str(corpus),
        "objects_fingerprinted": {k: len(v) for k, v in results.items()},
        "reference": reference_name,
        "identical": not failures,
        "differences": failures,
    }
    (workdir / "compute_mode_validation.json").write_text(
        json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k != "differences"},
                     indent=1))
    return 0 if not failures else 1


def _fingerprint_with_env(corpus: Path, pgdata: Path, env: dict) -> dict:
    """Fingerprint a run, applying the mode's environment to a child process."""
    out = pgdata.parent / f"run_{pgdata.name}"
    child_env = dict(os.environ)
    child_env.pop("COMPUTE_MODE", None)
    child_env.pop("COMPUTE_GATEWAY", None)
    child_env.update(env)
    cmd = [sys.executable, str(HERE / "soak_ingest.py"), str(corpus),
           "--out", str(out), "--label", f"modes_{pgdata.name}",
           "--workers", "4", "--max-conn", "25", "--pool", "8",
           "--pgdata", str(pgdata), "--sample-interval", "5"]
    completed = subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=3600,
                               env=child_env)
    # A mode whose ingest did not reach a clean end state is reported as a
    # failure even if its rows happen to match: "identical because the work was
    # skipped" is exactly the outcome this validator exists to rule out.
    if completed.returncode != 0:
        raise RuntimeError(f"{pgdata.name}: ingest exited with "
                           f"{completed.returncode}; see {out}/summary.json")
    summary_path = Path(out) / "summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text())
        ledger = summary.get("ledger", {})
        if ledger.get("files_pending"):
            raise RuntimeError(f"{pgdata.name}: {ledger['files_pending']} file(s) "
                               f"never reached a worker")
        if ledger.get("complete") is False:
            raise RuntimeError(f"{pgdata.name}: ledger did not complete: {ledger}")
    else:
        raise RuntimeError(f"{pgdata.name}: no summary.json written")
    return _read_fingerprints(pgdata)


def _read_fingerprints(pgdata: Path) -> dict:
    import urllib.parse

    import pgserver
    import psycopg2

    server = pgserver.get_server(str(pgdata))
    parsed = urllib.parse.urlparse(server.get_uri())
    host = urllib.parse.parse_qs(parsed.query).get("host", [""])[0]
    conn = psycopg2.connect(host=host, port=5432, user="postgres",
                            password="", dbname="analysis")
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT p.file_path, h.hash, p.file_type, p.file_status,
                   (SELECT count(*) FROM contents x WHERE x.path_id = p.id),
                   (SELECT count(*) FROM contents_raw cr0 WHERE cr0.path_id = p.id),
                   (SELECT count(*) FROM words_paths wp WHERE wp.path_id = p.id),
                   (SELECT count(*) FROM titles_content t WHERE t.path_id = p.id),
                   (SELECT COALESCE(sum(cr.char_count), 0)
                      FROM contents_raw cr WHERE cr.path_id = p.id),
                   (SELECT md5(string_agg(cr2.content, chr(10) ORDER BY cr2.chunk_seq))
                      FROM contents_raw cr2 WHERE cr2.path_id = p.id),
                   -- Sorted by word *value*: the multiset is the evidence, the
                   -- insertion-ordered word ids are an implementation detail.
                   (SELECT md5(string_agg(w.word, ',' ORDER BY w.word))
                      FROM words_paths wp JOIN words w ON w.id = wp.word_id
                     WHERE wp.path_id = p.id),
                   -- titles_content.title_data is bytea and, like
                   -- content_data, keyed by word ids; it is compared by row
                   -- count, not by bytes.
                   NULL
              FROM paths p
              JOIN hashs h ON h.id = p.hash_id
             ORDER BY p.file_path
        """)
        fingerprints = {}
        for (file_path, file_hash, file_type, file_status, content_rows,
             raw_rows, word_paths, title_rows, raw_chars, raw_digest,
             word_digest, _ignored) in cur.fetchall():
            fingerprints[file_path] = {
                "hash": file_hash,
                "type": file_type,
                "status": file_status,
                "content_rows": content_rows,
                "raw_rows": raw_rows,
                "title_rows": title_rows,
                "word_paths": word_paths,
                "raw_chars": raw_chars,
                "raw_digest": raw_digest,
                "word_digest": word_digest,
            }
        return fingerprints
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
