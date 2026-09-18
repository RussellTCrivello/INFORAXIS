# Document, artifact and compute architecture

This document describes the processing architecture as implemented, and states
plainly which parts are **verified on this machine**, which are **measured**, and
which are **not verified** because the hardware or a sample was unavailable.

The pipeline shape:

```
Input Artifact
   │
   ├─ Format identification      core/formats/{catalog,detection}.py
   │     content signature + container inspection → format id, family, MIME,
   │     version, features, declared-vs-detected discrepancies, reader routing
   │
   ├─ Workload classification    core/compute/routing.py
   │     workload kind → required capabilities, supported devices, preferred
   │     device, estimated CPU/memory/duration, accelerator memory requirement
   │
   ├─ Compute scheduler          core/compute/{gateway,backpressure}.py
   │     admission control · CPU queue ‖ accelerator queue · independent limits
   │
   ├─ Workers                    reader_file/readers/*, pipeline/integrated_reader.py
   │     one worker per unit of work, bounded window, timeouts, retry,
   │     checkpoint/resume, cooperative cancellation
   │
   ├─ Common artifact model      reader result dicts + pipeline/progress_ledger.py
   │     records every artifact once, with parent/child links and one terminal
   │     state per unit
   │
   └─ Storage / index / search   pipeline/storage_pipeline.py
         stored content (including forensic text), hashes, lineage, keywords
```

Every stage is additive to what existed: the readers, the router, the ledger and
the storage pipeline keep their previous contracts and gained no duplicate
pipelines. The new modules are consulted *by* the existing ones.

---

## 1. Format identification: what a file is, not what it is called

**Module:** `core/formats/catalog.py`, `core/formats/detection.py`

Identification is content-based and container-aware. The signature sniffer that
was already in production (`core/detect_binanry_utils.py`) answers "which magic
bytes matched"; the format service adds what a forensic record needs:

| Question | How it is answered |
| --- | --- |
| Which format is this *exactly*? | Container inspection: OOXML part list and content types, ODF `mimetype`, ZIP inventory, OLE stream names, PDF header/features, email headers. |
| Is it macro-enabled? | `vbaProject.bin`/`vbaData.xml` parts or a macro-enabled content type; legacy OLE `_VBA_PROJECT_CUR`/`Macros`/`VBA` storages. |
| Template, document or slideshow? | OOXML content types (`template.main+xml`, `slideshow.main+xml`) and, for legacy files, the Word FIB `fDot` bit and the Excel BIFF `dt` field. |
| Is it encrypted? | OOXML CFB `EncryptionInfo`+`EncryptedPackage`, ODF `manifest.xml` encryption data, Word FIB `fEncrypted`, PDF `/Encrypt`, encrypted ZIP entries. |
| Does the name disagree with the content? | Recorded as discrepancies with severities (`format_mismatch`, `variant_mismatch`, `binary_declared_as_text`, `extension_alias`, `encrypted_content`, `container_subtype`, …). Content decides the reader; the declared name is preserved. |

The catalogue holds **101 formats**; **151 extension spellings** are registered
with the readers that must accept them, and aliases (`.jfif` → `.jpg`) are
declared separately so that "the reader handles this" stays a checkable claim.
A test enforces that claim for every non-identified-only extension, which is how
identification and processing are prevented from drifting apart.

**Formats that are identified but not parsed** are declared `identified_only`
with a reason (`.cab`, `.iso`, `.Z`, `.psd`, `.dcm`, `.wmf`, `.mid`, `.mdb`,
`.accdb`, `.evt`, `.evtx`, `.hiv`, `.lnk`, `.one`, `.vhd`, `.wim`, executables,
`.bin`, `.m4a`). Such an artifact keeps its identity, MIME type and
discrepancies and is recorded **UNSUPPORTED** - an explicit terminal state - not
skipped and not handed to a reader that would mis-parse it.

Bounded cost: identification reads a header (default 8 KiB), a ZIP central
directory, small metadata parts (≤ 256 KiB) and, for compound files, the stream
directory. It never loads a document body.

## 2. Extraction: the body *and* everything around it

**Modules:** `core/forensics/{office_package,vba,pdf}.py`, `reader_file/readers/*`

| Family | Body extraction | Forensic detail added |
| --- | --- | --- |
| OOXML (document/template/slideshow/macro-enabled/binary workbook) | python-docx, openpyxl, python-pptx | core + application + **custom** properties, revisions (insertions, deletions, deleted text, authors), comments, hidden text/runs, fields, bookmarks, headers/footers, footnotes/endnotes, hyperlinks, external relationships, embedded objects, sheet states, defined names, formulas, hidden slides, speaker notes, slide comments, package inventory |
| Legacy OLE Office (`.doc/.dot/.xls/.xlt/.ppt/.pot/.pps/.msg`) | xlrd / OLE readers | FIB flags (template/encrypted), BIFF document type, stream inventory with digests, macro storage |
| OpenDocument (`.odt/.ott/.ods/.ots/.odp/.otp/.odg`) | odfpy plus package scan | metadata mirror in the same property keys, hidden sections, tracked changes, hyperlinks, bookmarks, field masters |
| PDF | page text with native/OCR layer classification | annotations (incl. their JavaScript and file attachments), embedded files (**materialised as child artifacts** with MD5/SHA-256), JavaScript, form fields and signature fields, outlines, incremental-revision count, catalog features |
| Email | `.eml`/`.mbox`/`.emlx` MIME parts, attachments, headers | Apple Mail `.emlx` byte-count line and plist flags recorded; mbox/RFC822 evidence required before a text-email parser is used |
| Archives | ZIP/TAR/GZ/BZ2/XZ/RAR/7Z plus compound `.tar.gz/.tgz/.tbz2/.txz` | per-entry inventory, encryption flags, nested document/archive counts, safety limits and skipped-member records |

**Macros** (`core/forensics/vba.py`) are handled for both container kinds: each
`vbaProject.bin` (or legacy `_VBA_PROJECT_CUR` storage) is hashed with MD5 and
SHA-256 and its size recorded; modules are decompressed through
`oletools`/`olevba` (MS-OVBA), together with the auto-execution/suspicious-keyword
analysis. A project that cannot be decompressed reports `extraction_error` *and
keeps its digests*, so "no macros" can never be confused with "macros we could
not read".

**Searchability:** the flattened detail (`forensic_text`) is merged into the
stored text by `pipeline/storage_pipeline._extract_text_from_content`, so a term
inside a tracked deletion, a comment, a PDF annotation or a macro is indexed.

**Failure handling:** every sub-extraction records its reason in
`extraction_errors`; skipped-for-size parts are named. A missing field means the
format does not have it, never that the extractor gave up silently.

## 3. Compute modes

**Module:** `core/compute/{capabilities,routing,gateway}.py`

| Mode | Semantics |
| --- | --- |
| `cpu` | Everything on the CPU. No accelerator is used, whatever hardware exists. |
| `gpu` | Every workload that *has* an accelerator implementation runs on the accelerator. If no verified device/backend exists, `DeviceUnavailableError` is raised with the detected-device report and a remediation hint - **no silent CPU substitution**. `COMPUTE_GPU_FALLBACK=1` opts into the old behaviour explicitly, and every fallback is recorded. Workloads with no accelerator implementation (hashing, extraction, indexing, compression, metadata) still run on the CPU: there, the CPU is the only implementation, not a fallback. |
| `cpu+gpu` | Both device sets are used concurrently with independent limits; accelerator-capable workloads are preferentially placed on accelerators, CPU-only workloads on the CPU. |
| `auto` | Routing from measured capability plus workload characteristics, with an explicit reason on every placement. |

Capability discovery (`core/compute/capabilities.py`) probes CPU, GPU (vendor
tooling/PyTorch/CUDA query), NPU, FPGA and DPU at runtime. **Nothing is claimed
that was not detected**: on a machine with no accelerator the report says so and
every workload is placed on the CPU with that reason.

Provenance: every execution records `execution_mode`, `selected_device`,
`actual_device`, `processor`, `duration_ms`, `outcome`, `fallback_reason` in a
bounded ring buffer (256) and in exact per-workload aggregates; `mode_report()`
publishes detected hardware (including accelerator memory), supported / CPU-only
/ unsupported workloads, placements with reasons, records, aggregates, strictness
and honest limits.

Fit matters as much as presence: a workload declares an accelerator memory
requirement, and a device whose capacity is unknown or too small is reported as
not fitting (`memory_fits`, `memory_note`).

## 4. Scheduling, backpressure and resource isolation

**Modules:** `core/compute/{gateway,backpressure}.py`,
`pipeline/integrated_reader.py`

* **Bounded queues and windows.** The reader keeps at most
  `configured_workers + max(1, workers//4)` units in flight; the compute gateway
  refuses work beyond its queue depth with `BackpressureError`. There is no path
  that creates workers without bound.
* **Dynamic admission control** (`AdmissionController`): samples CPU, memory and
  load (`psutil`, else `/proc/loadavg`), shrinks the window immediately under
  pressure (halving, floor 1) and grows it back one step at a time after a
  cooldown. Unmeasurable pressure leaves the configured window alone and says so
  instead of inventing a number. Every change records the measurement that caused
  it.
* **Overload never abandons a file.** A reduced window *delays submission*; it
  never drops work. The ledger, not the controller, owns accounting, and the
  identity `discovered = filed + pending` is asserted in tests and reported by
  `accounting()`.
* **Isolation.** `gateway.apply_isolation()` confines compute workers away from
  reserved gateway cores via CPU affinity where supported and a reduced
  scheduling priority otherwise, reporting what it could and could not do.
  Storage concurrency is bounded by a process-wide semaphore shared with the
  connection pool.
* **Timeouts, retry, cancellation, resume.** Per-file deadlines scale with size
  and observed throughput, capped by `max_file_timeout_s`; a container that keeps
  publishing children pushes its deadline back (stall detection rather than a
  fixed kill). Timed-out units settle as `retryable`; cancellation settles as
  `cancelled`; `CheckpointManager` skips already-processed files on resume, and
  duplicate-path reservation prevents two workers from processing the same file.

## 5. Accounting

**Module:** `pipeline/progress_ledger.py`

States: `DISCOVERED`, `QUEUED`, `PROCESSING`, `PROCESSED`, `STORED`, `INDEXED`,
`FAILED`, `SKIPPED`, `LOCKED`, `UNSUPPORTED`, `CANCELLED`, plus `RETRYABLE`.

Identity: `discovered = completed + failed + skipped + unsupported + retryable +
locked + cancelled + in_progress + pending`. `accounting()` returns the counts,
the transitional states, the unprocessed total, `invariant_holds` and `complete`
(complete = invariant holds and nothing pending or in progress). Lock-contention
errors (Windows sharing violations, `EAGAIN`/`EBUSY`, permission denied) classify
as `LOCKED`, not `FAILED`.

## 6. Verification status

| Capability | Status | Evidence |
| --- | --- | --- |
| Content-based identification incl. OOXML variant/macro distinction, ODF, archives, PDF features, email, legacy OLE (FIB/BIFF/variant/macros/encryption) | **verified** | `tests/unit/test_format_detection.py` (50 tests) with real compound-file fixtures |
| Catalogue ↔ reader coverage (no format identified but unroutable) | **verified** | `TestCatalogueIntegrity` in the same file |
| Forensic detail extraction (properties, revisions, comments, hidden content, fields, bookmarks, links, embeddings, sheet/slide state, formulas) | **verified** | `tests/unit/test_forensic_extraction.py` (21 tests) |
| PDF annotations, embedded files as child artifacts, form fields, revisions, encryption | **verified** | same file, built with PyMuPDF |
| Macro project discovery + hashing incl. failure recording | **verified** | same file (real CFB fixtures via the test-only writer) |
| Macro *decompression* (MS-OVBA) | **partially verified** | contract exercised with a stubbed `olevba` parser; no real macro-bearing sample exists in this environment, so decompression of a genuine project was not executed here |
| Compute modes: CPU-only, strict GPU refusal, CPU+GPU split, auto placement, provenance records, equivalence of output across modes | **verified for CPU-only / refusal / auto / cpu+gpu placement**; **not verified for real accelerator execution** | `tests/integration/test_compute_control_contract.py` (21 tests); no GPU/NPU/FPGA/DPU hardware on this machine |
| Workload profiles, accelerator-memory fit, admission control (throttling, hysteresis, bounded decisions, unmeasurable pressure, throttled-run completeness) | **verified** | same file plus the throttled-ingestion test in `test_forensic_extraction.py` |
| End-to-end ingestion at scale with full accounting | **measured** | 100 020 files / 436 MB → 160 020 units, 1 751.75 s, 57.1 files/s, 0 duplicates, 0 failed stores, `discovered = 140 021 + 135 + 0 + 19 864` (see `docs/scalability/soak_100k_new_build.json`) |
| Multi-TB / multi-million-file datasets | **not measured** | extrapolation only, labelled as such |
| GPU-only and CPU+GPU *forensic equivalence* on real hardware | **not verified** | requires accelerator hardware; the contract is enforced in code and tested with a stubbed backend |
| PST/OST message extraction | **not verified here** | the backend (`libpff`/`pypff`) is not installed in this environment; the reader reports the missing backend explicitly |

## 7. Evidence files

| File | Contents |
| --- | --- |
| `docs/scalability/soak_100k_new_build.json` | 100 020-file run: throughput, resources, storage counters, database row counts, ledger accounting |
| `docs/scalability/compute_mode_validation.json` | cross-mode object-level equivalence on a real corpus (identical: true) |
| `docs/scalability/crash_resume_measured.json` | crash/resume measurements (duplicates, completeness) |
| `docs/scalability/known_failures.txt` | the failing-test baseline the suite is compared against |
| `docs/IMPLEMENTATION_REPORT.md` | the implementation report for this change set |
