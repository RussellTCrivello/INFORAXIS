# The INFORAXIS domain model

This document describes the information INFORAXIS holds and the task domains it
organises work around. It is a description of what the repository already does,
written down once so that later work refers to it instead of re-deciding it.

Two different things are called "domain" and they must not be confused:

* the **information model** — the entities material passes through, from the
  origin it came from to what an analyst concluded about it (this section);
* the **task domains** — the areas of work the interface is organised around,
  declared in `core/interfaces/domains.py` (the next section).

---

## 1. Information model

The model is a chain. Each step is a table that already exists, created by the
migrations in `database/migrations/`, and each step narrows what is known.

```
Side ──────────┐
               ├──► Hash ──► Path ──┬──► Content (legacy bytea)
Source ────────┘                    ├──► Content chunks (contents_raw)
                                    ├──► Metadata / titles
                                    ├──► Words / Keywords
                                    ├──► Categories ──► Analyst categories
                                    └──► Analysis results / Errors
```

| Entity | Table | What it is | Written by |
| --- | --- | --- | --- |
| Side | `sides` | A party the material belongs to. | `Api/routes/sides.py` |
| Source | `sources` | Where material came from: a device, a mailbox, a transfer. | `Api/routes/sources.py` |
| Hash | `hashs` | The digest of an object, scoped to its source and side — the identity of the material. | `pipeline/` (`storage_pipeline.py`) |
| Path | `paths` | One object: name, location, size, type, status, error, when seen. | `pipeline/`, `readers/` |
| Content | `contents` (legacy), `contents_raw` (text chunks) | What was read out of the object. | `readers/` via the storage pipeline |
| Metadata | `titles_content` and the path columns | What the format itself said (titles, dates, authors). | `readers/` |
| Words / Keywords | `words`, `keywords` | Terms identified in the text, and the ones that matter. | `Api/routes/words.py`, `keywords.py` |
| Categories | `categorys`, `categories_words` | Definitions of what a term means, for automatic classification. | `Api/routes/categories.py` |
| Analyst categories | `m0009_analyst_categorization` tables | What a person decided, kept apart from automatic outcomes. | `Api/services/analyst_categories.py` |
| Analysis / Errors | `paths.file_status`, `paths.error_message`, `jobs`/`job_events` | What happened to the object: read, unread, failed, and why. | `services/jobs/`, pipeline |
| Related files | relations queries in `Api/utils/utils.py` | Objects related by hash, lineage or container membership. | `Api/routes/archives_api.py` |

Two invariants are worth stating because code depends on them:

* **A path is the unit of work.** Analysis, retry, classification, the original
  file viewer and the relations screen all address a `paths.id`. A hash is
  identity; a path is an occurrence of that identity in a source; several paths
  may share one hash (the same object delivered twice).
* **Nothing is destroyed to record what happened.** `file_status` and
  `error_message` describe an object that could not be read; the row stays, and
  so does the job that tried. Recovery reads them.

---

## 2. Task domains

Declared once, in `core/interfaces/domains.py`, and referenced by every
interface in the registry. A domain answers "what is this for?" — it is a
grouping of *work*, not a database schema and not a settings category.

| Domain | Label | What belongs there |
| --- | --- | --- |
| `WORK` | Work | The overview a session starts from. |
| `DISCOVER` | Discover | Finding and reading what is stored: library, search, sources, sides, words, categories, notifications. |
| `INGEST` | Ingest | Bringing material in, and the validation that precedes it. |
| `PROCESS` | Processing | Reading, extracting and storing (reserved: today these are jobs, reported under Operate). |
| `ANALYZE` | Analyze | Working the material: archives, paths, batches. |
| `CLASSIFY` | Classify | Deciding what material is: classification outcomes and analyst categories. |
| `REPORT` | Report | Summarising and presenting findings. |
| `OPERATE` | Operate | Running the system: jobs, recovery, operational tooling. |
| `ADMINISTRATION` | Administration | People, roles, audit, system health. |
| `SETTINGS` | Settings | Configuration of the product itself. |
| `SECURITY` | Security | Authentication and authorization surfaces (reserved: these are infrastructure endpoints today, classified in the endpoint inventory). |
| `INTERNAL` | Cross-cutting and internal | Surfaces the product needs but does not advertise, and features with no page. |

Notes on the mapping, so nobody has to guess later:

* `PROCESS` and `SECURITY` are declared but currently hold no interface: the
  processing engine reports through the job system (`OPERATE`), and
  authentication is infrastructure rather than a navigable interface. They are
  declared because they are real parts of the model that will hold interfaces
  as the shell is built — a domain is declared deliberately, never invented at
  a call site.
* `INTERNAL` holds both the diagnostics page (`concurrency_monitor`, kind
  `INTERNAL`, so it never appears in navigation) and cross-cutting features
  (`page_tips`), which have no page at all.
* An interface belongs to **exactly one** domain; `validate_registry` enforces
  it.

---

## 3. How the two relate

```
   information model                        task domains
   ────────────────                         ────────────
   Side / Source        ──►  Ingestion interfaces read and write them
   Hash / Path          ──►  Discover (library, archive), Analyze (paths, batches)
   Content / Metadata   ──►  Discover (search), Report
   Words / Keywords     ──►  Discover + Classify
   Categories           ──►  Classify
   Analysis / Errors    ──►  Operate (jobs, recovery)
   Related files        ──►  Analyze (relationships, timeline)
```

The registry's `settings` field is the third axis: an interface names the
`category.key` settings it consumes, so the product map, the data model and the
configuration model stay three references to the same things rather than three
copies of them.
