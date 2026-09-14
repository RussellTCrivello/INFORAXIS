# Core Data Pipeline — Source-First Audit and Remediation

Branch `arena/01a090de-file-analysis` · base `0afc8be` · Python 3.11.2 · PostgreSQL via `pgserver`

This audit treats the **data-analysis pipeline** as the product. Administrative
surfaces were not touched. Every claim below is tied to a file:line I read or a
command I ran in this session; where I could not verify something I say so.

---

## 1. The pipeline, as actually implemented

Traced through source, not documentation.

| Stage | Implementation | Notes |
|---|---|---|
| Source / acquisition | `core/file_utils.py::read_tree()` | recursive walk, symlink-loop guard, error entries retained |
| Identification | `reader_file/services/file_reader_service.py::resolve_type_for_file()` | **new** — magic bytes first, extension as fallback |
| Type detection | `core/detect_binanry_utils.py::detect_file_type_with_confidence()` | ~60 signatures + container probes |
| Routing | `reader_file/services/file_router_service.py::process_file()` | recursion limit 5 |
| Reading / decoding | `reader_file/readers/*` (10 readers) | encoding-aware text reader, `chardet` |
| Parsing / extraction | per-reader (`read_pdf`, `read_office`, …) | |
| Text assembly | `pipeline/storage_pipeline.py::_extract_text_from_content()` | 18 typed content branches, spatial ordering |
| Hashing | `core/hashing.py::hash_file()` | streamed, 1 MiB chunks |
| Deduplication | `database/services/dedup_service.py` | identity = `(hash, source_id, side_id)` |
| Persistence | `database/services/contents_db_service.py` via `StoragePipeline._store_file_sync()` | |
| Indexing | `words` / `words_paths` / `keywords_paths` + `m0002` indexes | |
| Search | `Api/services/search_service.py::full_text_search()` | ILIKE + relevance CASE |
| Display | `Api/services/file_preview.py`, `Api/blueprints/files.py` | image/pdf/docx/xlsx/text previews |

---

## 2. Data types: 159 extensions across 10 readers

Read live from the registry (`FileReaderService._extension_map`), not from docs.

| Reader | n | Extensions |
|---|---|---|
| `RemainingFileReader` | 74 | text/code/config: `.txt .md .log .json .xml .html .htm .yml .yaml .ini .cfg .conf .toml .csv .tsv .rtf .ics .sql .srt .vtt` + 30 source-code extensions |
| `OfficeFileReader` | 18 | `.doc .docx .docm .xls .xlsx .xlsm .xlsb .xlt .xltx .ppt .pptx .pot .potx .odt .ods .odp .csv .rtf` |
| `VideoFileReader` | 20 | `.mp4 .mkv .mov .avi .wmv .flv .mpeg .mpg .m2ts .mts .3gp .ogv .webm .asf .vob .rm .rmvb .divx .ts .m4v` |
| `AudioFileReader` | 15 | `.mp3 .wav .flac .aac .ogg .opus .m4a .aiff .wma .ape .tak .tta .wv .mpc .webm` |
| `ImageFileReader` | 12 | `.png .jpg .jpeg .gif .bmp .tiff .tif .webp .ico .heic .heif .svg` |
| `EbookFileReader` | 7 | `.epub .mobi .azw .azw3 .fb2 .lit .pdb` |
| `ArchiveFileReader` | 6 | `.zip .tar .gz .bz2 .rar .7z` |
| `DatabaseFileReader` | 6 | `.sqlite .sqlite3 .db .db3 .s3db .sdb` |
| `EmailFileReader` | 4 | `.eml .msg .mbox .pst` |
| `PDFFileReader` | 1 | `.pdf` |

### Classification (honest — verified at runtime vs source-only)

**FULLY SUPPORTED — verified end to end this session** (ingest → store → search):
PDF text layer, CSV, TXT, PNG, ZIP, GZIP, TAR.GZ, DOCX.
**JPEG + GPS EXIF** verified ingest → store, landing in `paths.coordinates`.

**PARTIALLY SUPPORTED — reader + fixture test passes, not driven end to end here:**
EML (`tests/unit/test_reader_matrix.py::test_email_fixture` PASSED), TAR.

**METADATA ONLY by design:** all 15 audio and 20 video extensions — `read_audio.py`
and `read_video.py` call `read_audio_file` / `read_video_file` and return tag
metadata; they extract no transcript or frames.

**KNOWN GAPS against the directive's §3 list:**
- **Not claimed at all:** camera RAW (`.cr2 .nef .arw .dng`), `.tgz/.tbz2/.txz`
  tar aliases, `.iso`, `.cab`, `.msi`, `.lnk`, DICOM. `.bin` is handled only as
  the unknown-content fallback.
- **Animated images:** `.gif`/`.webp` are read, but only the first frame is
  considered; no frame enumeration.
- **EXIF beyond GPS.** GPS *is* extracted and verified (see below). But
  `read_img_fast.py:175-177` reads **only** EXIF tag `34853` (the GPS IFD).
  Camera make/model (271/272), lens, exposure, `DateTimeOriginal` (36867),
  orientation and embedded thumbnails are **not** extracted. §6's "camera
  information" and "images containing thumbnails/previews" are therefore gaps.
- **Encrypted archives:** `extract_zip/tar/rar/7z` do not accept a password;
  an encrypted archive surfaces as an extraction error, not a distinct state.
- **Subtitles:** `.srt`/`.vtt` are read as text; no embedded-subtitle stream
  extraction from containers.

### EXIF GPS — verified working end to end at runtime

I initially wrote in this report that no EXIF/GPS extraction existed. **That
was wrong**; I re-read the source and then tested it. Chain:
`read_img_fast.py:175` reads tag 34853 → `_extract_gps_location()` (:495) →
`content['location']` → `StoragePipeline._extract_coordinates()` (:1422) →
`paths.coordinates` (:667).

Runtime proof with a real GPS-tagged JPEG (EXIF tag 34853 confirmed present):

```
location: {'latitude': 52.37, 'longitude': 4.891666666666667,
           'coordinates': '52.370000, 4.891667',
           'google_maps_url': 'https://www.google.com/maps?q=52.37,4.891666666666667'}
gps_extracted: True
storage _extract_coordinates -> 52.370000, 4.891667
```

Driven through the real pipeline into a real database:

```
DB paths row: ('geo.jpg', '52.370000, 4.891667', 'Unread')
```

---

## 3. File identification (was the worst defect — now fixed)

**Before:** `process_file()` read `file_info['extension']` and looked it up in a
dict. A working magic-byte detector existed in
`core/detect_binanry_utils.py` but was reachable **only** from `read_email.py`
for attachment renaming — dead code in the ingestion path.

Reproduced against the real router:

| File | Result before |
|---|---|
| real PNG, no extension | `"No file extension found"` — never processed |
| real ZIP, no extension | `"No file extension found"` — never extracted |
| real ZIP named `.bin` | `"Unsupported file type: .bin"` |
| real PNG named `.txt` | text reader — binary stored as mojibake |
| real PDF named `.docx` | python-docx — PDF never read |

**After** (`resolve_type_for_file`, strong magic bytes override the extension;
weak text heuristics only fill a gap):

| File | Result after |
|---|---|
| real PNG, no extension | image reader, OCR pipeline |
| real ZIP, no extension | extracted, children recursed |
| real ZIP named `.bin` | extracted, children recursed |
| real PNG named `.txt` | image reader, mismatch recorded |
| real PDF named `.docx` | PDF reader, mismatch recorded |

Also fixed inside the detector, as a precondition of trusting it:
- OLE sub-type probe searched **ASCII** for `WordDocument`; OLE stores directory
  names as **UTF-16LE**, so it could never match. `.doc/.xls/.ppt/.msg` now resolve.
- Unknown RIFF payload no longer claims `.webp`.
- OOXML requires `[Content_Types].xml`; EPUB requires `epub+zip`.
- OpenDocument is named `.odt/.ods/.odp`, not `.zip`.

---

## 4. Concrete defects found and fixed

| ID | Sev | Defect | Evidence | Commit |
|---|---|---|---|---|
| **DETECT-01** | P0 | Extension alone determined the processing path; extensionless files were dropped | 5 reproductions above | `10097f9` |
| **PDF-01** | P0 | `detect_pdf_type_early` divided by `min(3, len(doc))` → `ZeroDivisionError` on a 0-page PDF, reported as opaque `"division by zero"` | `{"error":"division by zero"}` | `1a5757f` |
| **PDF-02** | P0 | Pages with ≤30 chars of text were sent to OCR; when OCR was absent/empty/failed the **text layer was discarded** | `chars=10 → extracted=0`; `chars=40 → 41` | `1a5757f` |
| **ROUTE-01** | P0 | `.csv` claimed by 2 readers, first-wins gave the plain-text reader; `OfficeFileReader.read_csv_file` and `StoragePipeline._extract_csv_text` were **dead code** | registry dump + dead path at `storage_pipeline.py:2198` | `ed18180` |
| **HASH-01** | P0 | Files ≥100 MB got `sha256(path\|size\|mtime)` as their "content hash"; storage accepted it | 2 identical 105 MB files → hashes `72cc7a03…` vs `0ae4e4cb…`, real hash identical | `e67b38d` |
| **SEARCH-01** | P1 | Literal `'%'` in the relevance CASE + bound params → psycopg2 `IndexError`, caught and returned as **zero results for every query** | 5 markers → `total=0`, 5 × "Full-text search error" | `4b7c1ca` |

### Defect detail worth reading

**PDF-02** is the most damaging: a legitimate text PDF whose page holds fewer
than ~31 characters lost **100% of its content**. Cover pages, title pages,
stamps, signature blocks. On any host without tesseract this extended to every
sparse page. Measured before the fix:

```
chars=  10  extracted=0    methods={'ocr_skipped_tesseract_unavailable': 1}
chars=  26  extracted=0    methods={'ocr_skipped_tesseract_unavailable': 1}
chars= 40   extracted=41   methods={'direct_extraction': 1}
chars= 51   extracted=52   methods={'direct_extraction': 1}
```

OCR is now additive: it never replaces text that was already extracted.

**SEARCH-01** broke the acceptance criterion completely — content was stored and
indexed (48 words, 76 `words_paths`) but unfindable, and the API still returned
HTTP 200 with an empty list. Verified in isolation:

```
name ILIKE '%'  || %s || '%'   -> IndexError: tuple index out of range
name ILIKE '%%' || %s || '%%'  -> ok
name ILIKE '%'  || 'b' || '%'  -> ok   (no params => no interpolation)
```

8 occurrences fixed: 6 in `Api/services/search_service.py`, 2 in the duplicated
ranking expression in `Api/utils/utils.py`.

---

## 5. End-to-end runtime evidence

Real `IntegratedFileReader.process_folder()` → real `StoragePipeline` →
disposable PostgreSQL → real `SearchService`:

```
corpus: container(zip,no ext) honest.pdf misnamed.docx picture.txt sales.csv
Total files found: 5   Files processed: 5   Files stored in database: 6
paths 6 · hashs 6 · words 48 · words_paths 76 · contents 4

QUARTERLYLEDGER -> honest.pdf      (PDF text layer)
RENAMEDREPORT   -> misnamed.docx   (PDF named .docx  -> DETECT-01)
ARCHIVECHILD    -> nested.pdf      (extensionless ZIP -> nested PDF)
EMEA            -> sales.csv       (structured CSV cell -> ROUTE-01)
honest.pdf      -> honest.pdf      (filename)
search errors   -> 0
```

The 6th record is the ZIP's child PDF, so container recursion reaches the index.
Each marker resolves to exactly the file containing it.

---

## 6. Tests

| File | Tests |
|---|---|
| `tests/unit/test_type_detection.py` | 29 |
| `tests/unit/test_pdf_text_layer.py` | 18 |
| `tests/unit/test_reader_routing.py` | 17 |
| `tests/unit/test_hash_identity.py` | 31 |
| `tests/integration/test_large_file_dedup.py` | 1 |
| `tests/integration/test_search_after_ingest.py` | 7 |
| **Total new** | **103** |

**Every fix has a falsification check** — I reverted the fix and confirmed the
new tests fail:

| Fix | Result with fix reverted |
|---|---|
| PDF-01/02 | 15 of 18 fail |
| ROUTE-01 | 12 of 17 fail |
| HASH-01 | 5 of 32 fail (incl. the DB-backed test) |
| SEARCH-01 | 6 of 7 fail, original `IndexError` visible |

**Suite totals:** `192 passed` at base `0afc8be` → `295 passed` now.
`7 failed / 41 errors / 1 skipped` **identical at base and now** — all in
`tests/security/` and `tests/e2e/`. Root cause verified: `/auth/login` returns
**302 → /setup** in this sandbox, so `admin_client` fixtures error and
`test_login_brute_force_rate_limited` sees
`expected a 429 among [302, 302, ...]`. Environmental, not data-pipeline
defects; I did not touch them.

**ruff:** new test files clean; no touched source file's finding count increased
(`read_pdf.py` 94→84, `read_office.py` 254→245, `file_reader_service.py` 26→25).

---

## 7. Archive / container capability

`core/archive_safety.py` is genuinely good and I changed nothing in it:
`max_depth=8`, `max_files=10_000`, `max_bytes=2 GiB`, `max_file_size=512 MiB`,
`max_compression_ratio=500`, `timeout_seconds=600`, path-traversal rejection,
symlink/hardlink/device/FIFO refusal. Router recursion cap is 5
(`MAX_RECURSION_DEPTH`). Existing tests `tests/unit/test_archive_safety.py` pass.

---

## 8. Remaining limitations (reported, **not** changed — schema is off-limits per §20)

1. **Processing state is not distinguishable.** `paths.file_status` is
   `CHECK (file_status IN ('Read','Unread'))`. Measured behaviour: it encodes
   *content extracted* (`'Read'`) vs *no content extracted* (`'Unread'`) — the
   GPS-only JPEG above stored as `'Unread'` because OCR was unavailable, while
   the text PDFs stored as `'Read'`. It therefore cannot distinguish
   discovered / queued / processing / failed / skipped / unsupported /
   partially-processed, which §14 requires. A corrupt file and a legitimately
   empty one are indistinguishable. Fixing this needs a migration —
   **requires your approval**.
2. **`hierarchy_path` is a dead parameter.** It is accepted at
   `storage_pipeline.py:227` and `:2864` and passed at `:2905`, but never
   appears in any SQL statement. Container ancestry survives only as
   `titles_content.title_status` `'Main'`/`'Branch'` plus the self-referencing
   `title_content_id`; there is no explicit parent-container column on `paths`.
3. **EXIF extraction is GPS-only.** Tag 34853 is read and lands in
   `paths.coordinates` (verified above), but no other EXIF field is extracted —
   no camera make/model, lens, exposure, `DateTimeOriginal`, orientation or
   embedded thumbnail. §6's "camera information" is unmet.
4. **No FTS index for content search.** Verified: `m0004_remove_pg_trgm.py`
   drops `idx_words_word_gin` and the `pg_trgm` extension, and no `tsvector` or
   `GIN` index exists in any migration. So `ILIKE '%term%'` is a sequential
   scan — correct, but slow at scale. Adding an index needs approval.
5. **CSV row cap is new.** `MAX_CSV_ROWS = 200_000`; beyond that rows are
   counted and reported as truncated rather than retained. Necessary because
   ROUTE-01 moved large CSVs into a reader that materialises rows.
6. **Duplicate `ranking` SQL** in `search_service.py` and `Api/utils/utils.py` —
   the same bug existed in both. Should be unified.
7. **`.ts` and `.webm` are genuinely ambiguous** (TypeScript vs MPEG-TS, audio
   vs video). Resolved explicitly in `EXTENSION_PREFERENCES` and logged, but the
   ambiguity is real.

---

## 9. Performance / resource observations

- **Hashing** is streamed at 1 MiB chunks — memory is O(chunk), not O(file).
- **Discovery no longer hashes files ≥100 MB**; storage computes the real hash
  once. This avoids a double full read of large files.
- **Header sniffing** reads a bounded 36 KiB per file (`SNIFF_HEADER_SIZE`),
  never the whole file.
- **PDF** rasterises only pages below the text threshold, and skips rasterising
  entirely when tesseract is absent — previously it rasterised every page and
  then discarded the result.
- **Unmeasured:** I did not benchmark wall-clock throughput at scale. The
  directive says prove correctness first, then measure; correctness is now
  proven, measurement is the next step.

---

## 10. Commits

```
4b7c1ca fix(SEARCH-01): full-text search returned zero results for every query
e67b38d fix(HASH-01): never fabricate a content identity from path and mtime
ed18180 fix(ROUTE-01): resolve reader conflicts explicitly; CSV gets real structure
1a5757f fix(PDF-01/02): never discard a PDF page's own text layer
10097f9 fix(DETECT-01): identify files by content, not by extension alone
```

All five pushed to `origin/arena/01a090de-file-analysis`. One defect per commit,
no mixed concerns. No database was dropped, reset, or repopulated — every test
uses a disposable `pgserver` instance.

---

## 11. Verdict against §22

`READ → IDENTIFY → PROCESS → EXTRACT → ENRICH → HASH → STORE → INDEX → SEARCH`
is now demonstrated end to end on real files through real code, for PDF, CSV,
text, image and nested-archive content.

**Not yet complete**, and I am not claiming it:
- OCR was exercised only on the "engine absent" path — **tesseract is not
  installed in this sandbox**, so §7's OCR matrix (rotated text, low-quality
  scans, multiple languages, scanned PDFs) is unverified. This is the single
  largest evidence gap.
- Display/preview (§12) and XSS escaping of extracted content were read but not
  exercised at runtime.
- Concurrency, crash recovery and retry behaviour (§14–15) were not tested.
- Processing-state observability is blocked on the schema limitation above.

Suggested order for the next units: install tesseract and verify the OCR
matrix; then unify the duplicated ranking SQL; then, **with approval**, a
migration for `paths.file_status` granularity.
