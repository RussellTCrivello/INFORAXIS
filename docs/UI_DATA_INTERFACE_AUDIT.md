# INFORAXIS Data Interface Audit

Date: 2026-09-16

This audit enumerates the structured-data and Add/Create interfaces reviewed for the application-wide data-interface enhancement. The target interaction model is codified in `docs/ENTERPRISE_DATA_WORKSPACE_BLUEPRINT.md`: a high-density enterprise workspace where the data workbench is the primary product surface.

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

- `static/css/styles.css`: rebuilt as the clean enterprise foundation for global layout, navigation, surfaces, controls, cards, modals, tables, pagination, states, RTL and responsive behavior.
- `static/css/design-system.css` and `static/css/responsive-fixes.css`: reduced to compatibility layers so old duplicate dashboard-era styling no longer competes with the unified foundation.
- `static/css/data-interface.css`: shared enterprise workspace shell, light/dark theme tokens, density modes, table workbench controls, status badge, record-list/card, modal and form tokens, plus the fixed-control/scrolling-data contract.
- `static/js/modules/core/data-interface.js`: progressive enhancement for all Jinja-rendered and dynamically rendered tables/modals, including automatic classification of toolbar/filter/sort/search surfaces as stable controls and result/table/list/grid containers as scroll regions.
- Global table workbench controls provide per-table search, multi-column sorting, grouped column visibility, saved views, row counts, persistent density/preferences, keyboard row navigation, and expandable row detail summaries.
- A global command/search palette (`Ctrl/Cmd+K`) exposes navigation, create/import/export actions, density controls, theme switching, and workspace preference reset.
- A contextual selection bar appears when table rows are selected and proxies available page bulk actions without replacing existing backend workflows.
- Source and side management now share table/list generation plus local Add/Edit/Duplicate/Delete updates, preserving context without forcing a reload.
- Page CSS was cleaned into structural, token-based layout-only files for data management, analysis, search, notifications, settings, upload, chart, formatted-content, auth and setup interfaces.
- Standalone auth/setup pages now share `static/css/auth-workspace.css`; their former large inline style blocks were removed.
- Template-level cleanup moved obsolete static inline layout/visual styles into reusable classes; remaining inline styles are limited to runtime visibility toggles, progress widths and user-configurable theme swatch colors.
- Dynamically generated FMAS/file/source/category/search/path-analysis/notification renderers now use shared CSS classes for analogous cards, rows, numbered file badges, metadata chips, result cards, and selected-word badges instead of conflicting per-renderer inline visual styles.

## Interaction principles

- Keep existing server filtering, permissions and validation intact.
- Add client-side sorting only to safe, visible table columns without replacing server-side filters.
- Apply semantic cell treatments based on headers/data type: identifiers, numbers, sizes, dates, statuses, paths and actions.
- Preserve high-density scanning while exposing full long values through titles/truncation.
- Keep controls such as filters, sort workbenches, search bars, contextual actions and pagination stable while table rows/result cards own the scrolling.
- Add modal focus management, required-field marking, validation focus, keyboard submit and consistent disabled/loading states.
