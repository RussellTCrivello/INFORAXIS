# INFORAXIS Enterprise Data Workspace Blueprint

Date: 2026-09-16  
Branch: `arena/01a0ac6a-inforaxis`

## Purpose

This blueprint translates the supplied reference direction into an implementation standard for INFORAXIS. The target is a premium analytical instrument: a high-density workspace where structured data is the primary product surface, not a dashboard full of disconnected cards.

## Core model

Every major interface should resolve to this architecture:

```text
Application shell
  → persistent navigation
  → compact workspace header
  → view/search/filter/sort/action controls
  → optional contextual analytics strip
  → data workbench
  → contextual selection actions
  → pagination/status
```

The table, list, grid, or record surface is not secondary. It is the workspace.

## Design language

The shared language is intentionally quiet and precise:

- High information density.
- Compact controls.
- Thin separators instead of heavy cards.
- Neutral color as the default; semantic color only when it communicates state.
- Small status/tag pills rather than large colored blocks.
- Tight but readable typography.
- Lightweight hover/focus states.
- Contextual actions instead of permanently visible action clutter.
- Persistent navigation and workspace state.
- Professional light/dark themes.

Avoid:

- Decorative gradients on working surfaces.
- Oversized cards/buttons where dense controls are more appropriate.
- Isolated page-specific styling for analogous records.
- JavaScript layout mutation that competes with CSS.
- Native browser `alert()`/`confirm()` for normal enterprise workflows.

## Required workspace layers

### 1. Global application functions

- Persistent left navigation.
- Global search / command palette.
- Quick actions.
- Notifications.
- Settings and account controls.
- Help/onboarding entry points.
- Pinned or frequently used workspace views where useful.

### 2. Dataset functions

Every record-oriented interface should support or progressively inherit:

- Search.
- Advanced filter builder.
- Sort and multi-sort.
- Saved views.
- View switching: table/list/board where useful.
- View settings.
- Column visibility, grouping, ordering, and eventually resize/pin/freeze.
- Import/export from the current analytical context.
- Result counts and server-side pagination awareness.
- Density control.

### 3. Record functions

- Select and multi-select.
- Open/drill down.
- Expand details.
- Edit or inline-edit where safe.
- Delete/duplicate/tag/categorize/assign/status changes where permissions allow.
- Row or cell context menus.

### 4. Bulk/contextual functions

Bulk controls should appear only when relevant:

- Selection count.
- Bulk export.
- Bulk categorize/tag/assign/status change.
- Bulk delete when permitted.
- Clear selection.

### 5. Presentation functions

- Compact data tables as the default for large datasets.
- List/card/board modes only as alternate views over the same underlying dataset.
- Consistent missing-value treatment.
- Subtle metadata and relationship indicators.
- Expandable row/detail areas instead of forcing full page navigation for every detail.

## Fixed-control / scrolling-data rule

Controls stay stable. Data moves.

Controls include:

- Navigation tabs.
- Search bars.
- Filters and filter chips.
- Sort controls.
- View settings.
- Column controls.
- Import/export/create actions.
- Pagination and result summaries.
- Contextual selection bars.

Data regions include:

- Table bodies/wrappers.
- Result lists.
- File/record grids.
- Relationship lists.
- Notification lists.
- Search results.
- Modal result panes.

Implementation should prefer explicit roles:

```html
<div data-ia-role="controls">...</div>
<div data-ia-role="data-region">...</div>
```

Selector inference in `data-interface.js` is a fallback, not a substitute for intentional markup.

Opt out when necessary:

```html
<div data-ia-sticky="false">...</div>
<div data-ia-scroll="false">...</div>
```

## Advanced filter builder standard

The desired filter model is structured and composable:

```text
WHERE
  Field  Operator  Value
AND
  Field  Operator  Value
```

Minimum behavior:

- Add/remove conditions.
- Field selection.
- Operator selection.
- Type-aware values.
- Visible active filter chips.
- Save filters as part of saved views.

Preferred behavior:

- Floating filter panel instead of permanent large forms.
- Logical operators.
- Reusable condition model across pages.
- Keyboard access.

## Saved views standard

A saved view should preserve:

- Search query.
- Filters.
- Sort/multi-sort.
- Visible columns.
- Column order/grouping.
- View type.
- Density.
- Page size.
- Optional group/aggregation state.

Saved views should never mutate the underlying dataset; they are analytical perspectives.

## Table/grid standard

Tables should use:

- Compact row height.
- Sticky, understated headers.
- Column type indicators where helpful.
- Sorting affordances.
- Selection checkbox column when bulk actions exist.
- Low-emphasis unavailable values.
- Semantic status/tag pills.
- Inline metadata.
- Row hover and focus states.
- Expandable details for secondary information.
- Context menus for less common actions.

## Master/detail standard

Record-heavy workflows should support a path from dataset to detail without losing context:

- Expandable row detail.
- Side drawer.
- Split pane.
- Dedicated detail view with a sticky action/header strip.

The list/table state should persist when moving into and back from detail.

## Responsive behavior

The table should not simply shrink until unreadable. Responsive behavior should:

- Collapse navigation appropriately.
- Keep data controls accessible.
- Preserve horizontal scrolling for dense tables.
- Move lower-priority fields into hidden columns, detail panels, or expanded rows.
- Keep pagination/result context visible.
- Avoid JavaScript layout mutation; CSS owns responsive layout.

## Current implementation anchors

The current branch already includes the main foundation:

- `static/css/styles.css` for the global shell and enterprise primitives.
- `static/css/data-interface.css` for workbench/data-interface behavior.
- `static/js/modules/core/data-interface.js` for progressive table/modal/workbench enhancement.
- `static/js/responsive-fixes.js` now limited to semantic responsive table metadata, not layout overrides.
- `docs/UI_LEGACY_DESIGN_AUDIT.md` for the remaining modernization backlog.

## Immediate enforcement priorities

1. Do not introduce new broad page CSS for reusable component names.
2. Do not introduce static inline styles for spacing/color/border/shadow/layout.
3. Do not add JavaScript that mutates responsive layout styles.
4. Mark controls/data regions explicitly in new markup.
5. Route new record tables through the data-interface workbench.
6. Use the shared chart empty/loading states for all chart pages.
7. Keep card-heavy dashboard patterns secondary to data workspaces.

## Definition of done for future UI work

A page is aligned with this blueprint when:

- The data workspace is the dominant surface.
- Controls remain stable while data regions scroll.
- Search/filter/sort/view/pagination controls are compact and close to the data.
- Bulk/contextual actions appear only when relevant.
- Tables/lists/cards use shared record primitives.
- Preferences and saved views persist where appropriate.
- Light/dark themes and density modes remain coherent.
- Responsive behavior preserves analytical usability.
