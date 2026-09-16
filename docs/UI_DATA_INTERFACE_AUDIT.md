# INFORAXIS Data Interface Audit

Date: 2026-09-16

This audit enumerates the structured-data and Add/Create interfaces reviewed for the application-wide data-interface enhancement.

## Structured and tabular surfaces

- Analysis batch: selected-files table and failed-files history table.
- Dashboard: largest-files table.
- Analyst categorization: analyst assignments table and audit/list sections.
- Categories: grid/list/compact/table views, category-word relationship table.
- Keywords: keyword management table, filtering, selection and Add Keyword flow.
- Operations: jobs table, job event/error tables, operations widget tables, import/input quick-create selectors.
- Settings: API/endpoints metadata table and theme table controls.
- Users: accounts table and role capability matrix.
- Email words: email-address table and related-file modal list.
- File detail: metadata, keyword frequency and hash/detail tables.
- File library: primary files table plus card/grid view.
- Sources and sides: card/list workflows upgraded with generated dense table and compact list views.

## Add/Create and modal surfaces

- Add Category and Add Word to Category.
- Add Word.
- Add Keyword.
- Add Source and Add Side.
- Input / Ingestion inline quick-create source/side workflow.
- Add User and password/reset/delete administration modals.
- File-management-system legacy Add Source, Add Side, Add Keyword, Add Category and relationship modals.
- Change Password modal.
- Preview/detail/history/template modals reviewed for shared modal shell consistency.

## Reusable system introduced

- `static/css/data-interface.css`: shared density, table, status badge, record-list/card, modal and form tokens.
- `static/js/modules/core/data-interface.js`: progressive enhancement for all Jinja-rendered and dynamically rendered tables/modals.
- Source and side management now share table/list generation plus local Add/Edit/Duplicate/Delete updates, preserving context without forcing a reload.

## Interaction principles

- Keep existing server filtering, permissions and validation intact.
- Add client-side sorting only to safe, visible table columns without replacing server-side filters.
- Apply semantic cell treatments based on headers/data type: identifiers, numbers, sizes, dates, statuses, paths and actions.
- Preserve high-density scanning while exposing full long values through titles/truncation.
- Add modal focus management, required-field marking, validation focus, keyboard submit and consistent disabled/loading states.
