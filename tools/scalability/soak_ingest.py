#!/usr/bin/env python3
"""End-to-end scalability/soak harness for the INFORAXIS ingestion pipeline.

Runs the *real* pipeline (IntegratedFileReader -> FileRouterService -> readers
-> StoragePipeline -> PostgreSQL) over a generated corpus and samples resource
usage continuously, so throughput and memory can be compared between dataset
sizes and across long runs.

What it measures (all from the running process, not estimated):

  * throughput now vs. the first/middle/last decile of the run (progressive
    degradation would show up as a falling last-decile rate);
  * resident memory at the same points (leaks / unbounded growth);
  * open file descriptors, live threads, live PostgreSQL backends;
  * per-file cost (ms/file) and per-byte cost (MB/s);
  * exact accounting - discovered / done / stored / duplicates / failed /
    skipped / unsupported / pending - cross-checked against the database;
  * retry counts, error rates and the error classes behind them;
  * database size, index size and per-table row counts after the run;
  * duplicate detection at both levels: duplicate hash groups (same content)
    and duplicate path rows (same file stored twice - the "no duplicate
    processing" property).

Usage:
    soak_ingest.py <corpus> --out <dir> [--workers N] [--max-conn N] [--pool N]
                   [--label NAME] [--checkpoint-file P] [--kill-after S]
                   [--pgdata DIR] [--sample-interval S]

``--pgdata`` reuses an existing database directory, which is what makes
crash/restart testing meaningful: kill a run with ``--kill-after``, then rerun
with the same ``--pgdata`` and ``--checkpoint-file`` and compare.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = Path(os.environ.get("REPRO_REPO", HERE.parents[1])).resolve()
sys.path.insert(0, str(PROJECT_ROOT))

import psutil  # noqa: E402
import psycopg2  # noqa: E402
import pgserver  # noqa: E402

START = time.time()


def _json_default(value):
    """Serialize the odds and ends the pipeline exposes (Decimal, Path, set)."""
    from decimal import Decimal

    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (set, frozenset)):
        return sorted(str(v) for v in value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


class Capture(logging.Handler):
    """Every record the pipeline emits, with level and logger name."""

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []
        self._lock = threading.Lock()

    def emit(self, record):
        try:
            msg = record.getMessage()
        except Exception:
            msg = "<unformattable>"
        with self._lock:
            self.records.append({
                "level": record.levelname,
                "logger": record.name,
                "msg": msg[:400],
                "thread": record.threadName,
                "t": round(time.time() - START, 3),
            })


class Sampler(threading.Thread):
    """Background resource sampler."""

    def __init__(self, interval=1.0, db_cfg=None):
        super().__init__(daemon=True)
        self.interval = interval
        self.db_cfg = db_cfg
        self.stop_event = threading.Event()
        self.samples = []
        self._process = psutil.Process()

    def _db_clients(self) -> int:
        if not self.db_cfg:
            return 0
        try:
            conn = psycopg2.connect(connect_timeout=2, **self.db_cfg)
            try:
                cur = conn.cursor()
                cur.execute("SELECT count(*) FROM pg_stat_activity WHERE "
                            "datname = current_database()")
                return cur.fetchone()[0]
            finally:
                conn.close()
        except Exception:
            return 0

    def run(self):
        while not self.stop_event.wait(self.interval):
            try:
                info = self._process.memory_info()
                with self._process.oneshot():
                    sample = {
                        "t": round(time.time() - START, 2),
                        "rss_mb": round(info.rss / 1e6, 1),
                        "vms_mb": round(info.vms / 1e6, 1),
                        "threads": self._process.num_threads(),
                        "fds": self._process.num_fds() if hasattr(self._process, "num_fds") else 0,
                        "cpu_percent": self._process.cpu_percent(None),
                        "io_read_mb": round(
                            self._process.io_counters().read_bytes / 1e6, 1),
                        "io_write_mb": round(
                            self._process.io_counters().write_bytes / 1e6, 1),
                    }
                sample["db_clients"] = self._db_clients()
                self.samples.append(sample)
            except Exception:
                continue


def _start_server(args):
    """Start (or reuse) the database this run measures against."""
    if args.pgdata:
        if not os.path.exists(os.path.join(args.pgdata, "PG_VERSION")):
            os.makedirs(args.pgdata, exist_ok=True)
            pgserver.initdb(["-U", "postgres", "-A", "trust", "-E", "UTF8"],
                            pgdata=args.pgdata)
            with open(os.path.join(args.pgdata, "postgresql.conf"), "a") as fh:
                fh.write("\nmax_connections = %d\n" % int(args.max_conn))
        return pgserver.get_server(args.pgdata)
    import tempfile

    data = tempfile.mkdtemp(prefix="pgdata_")
    pgserver.initdb(["-U", "postgres", "-A", "trust", "-E", "UTF8"], pgdata=data)
    with open(os.path.join(data, "postgresql.conf"), "a") as fh:
        fh.write("\nmax_connections = %d\n" % int(args.max_conn))
    return pgserver.get_server(data)


def _configure_env(server, db_name="analysis"):
    import urllib.parse

    uri = server.get_uri()
    parsed = urllib.parse.urlparse(uri)
    query = urllib.parse.parse_qs(parsed.query)
    host = query.get("host", [""])[0]
    os.environ.update(DB_HOST=host, DB_PORT="5432", DB_USER="postgres",
                      DB_PASSWORD="", DB_NAME=db_name)
    return dict(host=host, port=5432, user="postgres", password="",
                database=db_name)


def _corpus_inventory(root):
    files = 0
    total = 0
    for _root, _dirs, names in os.walk(root):
        for name in names:
            files += 1
            try:
                total += os.path.getsize(os.path.join(_root, name))
            except OSError:
                pass
    return files, total


def _db_facts(db_cfg):
    facts = {}
    try:
        conn = psycopg2.connect(connect_timeout=5, **db_cfg)
        cur = conn.cursor()
        for table in ("paths", "contents", "hashs", "titles_content", "words",
                      "sources", "sides", "keywords", "alerts"):
            try:
                cur.execute(f"SELECT count(*) FROM {table}")
                facts[f"{table}_rows"] = cur.fetchone()[0]
            except Exception as exc:
                facts[f"{table}_rows"] = f"error: {type(exc).__name__}"
        cur.execute("SELECT count(*) FROM (SELECT hash FROM hashs GROUP BY hash "
                    "HAVING count(*) > 1) dup")
        facts["duplicate_hash_groups"] = cur.fetchone()[0]
        # Duplicate *processing* shows up as the same file path stored twice.
        cur.execute("SELECT count(*) FROM (SELECT file_path FROM paths "
                    "GROUP BY file_path HAVING count(*) > 1) dup_paths")
        facts["duplicate_path_rows"] = cur.fetchone()[0]
        cur.execute("SELECT pg_database_size(current_database())")
        facts["db_size_bytes"] = cur.fetchone()[0]
        cur.execute("SELECT sum(pg_relation_size(indexrelid)) "
                    "FROM pg_stat_user_indexes")
        facts["index_size_bytes"] = cur.fetchone()[0] or 0
        cur.execute("SELECT count(*) FROM paths p LEFT JOIN hashs h ON "
                    "p.hash_id = h.id WHERE h.id IS NULL")
        facts["paths_without_hash_row"] = cur.fetchone()[0]
        # Referential integrity of the content index.
        cur.execute("SELECT count(*) FROM contents c LEFT JOIN paths p ON "
                    "c.path_id = p.id WHERE p.id IS NULL")
        facts["contents_without_path_row"] = cur.fetchone()[0]
        conn.close()
    except Exception as exc:
        facts["error"] = f"{type(exc).__name__}: {exc}"
    return facts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("corpus")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-conn", type=int, default=25)
    ap.add_argument("--pool", type=int, default=8)
    ap.add_argument("--checkpoint-file", default=None)
    ap.add_argument("--label", default="run")
    ap.add_argument("--kill-after", type=float, default=None,
                    help="hard-kill the process after N seconds (crash test)")
    ap.add_argument("--sample-interval", type=float, default=1.0)
    ap.add_argument("--pgdata", default=None,
                    help="reuse an existing pgserver data directory (crash/resume)")
    args = ap.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    server = _start_server(args)
    db_cfg = _configure_env(server)
    os.environ["INGESTION_ROOTS"] = str(Path(args.corpus).resolve())
    os.environ["DB_POOL_MAX"] = str(args.pool)
    os.environ["DB_POOL_MIN"] = "1"

    import core.resource_coordinator as rc

    rc.get_safe_worker_count = lambda requested=None: int(args.workers)
    rc.get_safe_db_pool_size = lambda requested=None: int(args.pool)

    from database.bootstrap import bootstrap_database

    bootstrap_database(db_cfg)

    corpus_files, corpus_bytes = _corpus_inventory(args.corpus)

    capture = Capture()
    logging.getLogger().addHandler(capture)
    logging.getLogger().setLevel(logging.DEBUG)

    from pipeline.integrated_reader import IntegratedFileReader

    sampler = Sampler(interval=args.sample_interval, db_cfg=db_cfg)
    sampler.start()

    if args.kill_after:
        def _killer():
            time.sleep(args.kill_after)
            print(f"KILLING PROCESS after {args.kill_after}s (crash test)", flush=True)
            os._exit(137)

        threading.Thread(target=_killer, daemon=True).start()

    reader = IntegratedFileReader(
        max_workers=args.workers,
        enable_monitoring=True,
        enable_storage=True,
        storage_source=f"soak_{args.label}",
        storage_side="soak_side",
        checkpoint_file=args.checkpoint_file,
    )

    t0 = time.time()
    error = None
    try:
        with reader:
            reader.process_folder(args.corpus)
    except Exception:
        import traceback

        error = traceback.format_exc()
    elapsed = time.time() - t0

    stats = {}
    live = {}
    storage_stats = {}
    for name, getter in (("stats", reader.get_statistics),
                         ("live", reader.get_live_progress),
                         ("storage", reader.get_storage_statistics)):
        try:
            value = getter()
        except Exception:
            value = {}
        if name == "stats":
            stats = value
        elif name == "live":
            live = value
        else:
            storage_stats = value

    time.sleep(max(2.0, args.sample_interval * 2))
    sampler.stop_event.set()
    sampler.join(timeout=5)

    db_facts = _db_facts(db_cfg)
    records = capture.records

    # ---- throughput at increasing progress points --------------------------
    progress = [(r["t"], r["msg"]) for r in records
                if isinstance(r.get("msg"), str) and r["msg"].startswith("Progress: ")]
    rates = {}
    if progress:
        marks = []
        for moment, message in progress:
            try:
                done, total = message.split(" ", 1)[1].split("/")
                marks.append((moment, int(done), int(total)))
            except Exception:
                continue
        if marks:
            last_total = marks[-1][2] or 1
            buckets = {"first_decile": (0.0, 0.1), "mid": (0.4, 0.6),
                       "last_decile": (0.9, 1.0)}
            for name, (low, high) in buckets.items():
                window = [(t, d) for t, d, _ in marks
                          if low <= d / last_total <= high]
                if len(window) >= 2:
                    span = max(0.001, window[-1][0] - window[0][0])
                    rates[f"rate_{name}_fps"] = round(
                        (window[-1][1] - window[0][1]) / span, 2)

    levels = Counter(r["level"] for r in records)

    def log_count(needle):
        return sum(1 for r in records if needle.lower() in r["msg"].lower())

    summary = {
        "label": args.label,
        "corpus": args.corpus,
        "corpus_files": corpus_files,
        "corpus_bytes": corpus_bytes,
        "corpus_gb": round(corpus_bytes / 1e9, 4),
        "elapsed_s": round(elapsed, 2),
        "exit_error": error.splitlines()[-1] if error else None,
        "files_per_second": round(corpus_files / elapsed, 2) if elapsed else None,
        "mb_per_second": round(corpus_bytes / 1e6 / elapsed, 3) if elapsed else None,
        "ms_per_file": round(elapsed * 1000 / corpus_files, 3) if corpus_files else None,
        **rates,
        "rss_start_mb": sampler.samples[0]["rss_mb"] if sampler.samples else None,
        "rss_end_mb": sampler.samples[-1]["rss_mb"] if sampler.samples else None,
        "rss_max_mb": max((s["rss_mb"] for s in sampler.samples), default=None),
        "rss_growth_mb": (round(sampler.samples[-1]["rss_mb"]
                                - sampler.samples[0]["rss_mb"], 1)
                          if len(sampler.samples) > 1 else None),
        "fd_start": sampler.samples[0]["fds"] if sampler.samples else None,
        "fd_max": max((s["fds"] for s in sampler.samples), default=None),
        "fd_end": sampler.samples[-1]["fds"] if sampler.samples else None,
        "fd_soft_limit": str(resource_limit()),
        "threads_max": max((s["threads"] for s in sampler.samples), default=None),
        "threads_end": sampler.samples[-1]["threads"] if sampler.samples else None,
        "cpu_percent_mean": round(
            sum(s["cpu_percent"] for s in sampler.samples) / len(sampler.samples), 1)
        if sampler.samples else None,
        "cpu_percent_max": max((s["cpu_percent"] for s in sampler.samples),
                               default=None),
        "db_clients_max": max((s["db_clients"] for s in sampler.samples), default=None),
        "samples": len(sampler.samples),
        "ledger": live or {k: v for k, v in stats.items()},
        "stats": stats,
        "storage_stats": storage_stats,
        "db": db_facts,
        "log_counts": {
            "errors": levels.get("ERROR", 0),
            "warnings": levels.get("WARNING", 0),
            "total_records": len(records),
            "retry": log_count("retry"),
            "ocr_unavailable": log_count("no engine is available"),
            "storage_failures": log_count("FAILED TO STORE"),
            "no_files_stored": log_count("no files were stored"),
            "pool_exhausted_timeouts": log_count("pool exhausted"),
            "too_many_clients": log_count("too many clients"),
            "reconnects": log_count("reconnect"),
        },
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=1, default=_json_default))
    (out_dir / "samples.json").write_text(
        json.dumps(sampler.samples, indent=1, default=_json_default))
    (out_dir / "records.json").write_text(
        json.dumps(records[:200000], indent=1, default=_json_default))
    print(json.dumps({k: v for k, v in summary.items()
                      if k not in ("stats", "ledger", "db", "storage_stats")},
                     indent=1, default=_json_default))
    return 0


def resource_limit():
    try:
        import resource

        return resource.getrlimit(resource.RLIMIT_NOFILE)[0]
    except Exception:
        return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
