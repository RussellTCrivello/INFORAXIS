# INFORAXIS Legacy / Outdated Design Audit

Date: 2026-09-16  
Branch: `arena/01a0ac6a-inforaxis`  
Baseline audited commit: `13fc114` (`Complete enterprise UI cleanup and fixed controls`)

## 1. Purpose

This audit focuses specifically on outdated or legacy design patterns that can disrupt the modern enterprise workspace direction: dense data analysis layouts, fixed controls with scrolling data regions, consistent record/card formatting, polished light/dark themes, stable workbench controls, and reusable interface patterns.

The supplied reference benchmark is now codified in `docs/ENTERPRISE_DATA_WORKSPACE_BLUEPRINT.md`: data is the workspace, controls are compact and persistent, contextual actions appear only when relevant, and visual emphasis stays quiet/semantic rather than card-heavy or decorative.

The goal is not to re-list every already-cleaned file. It is to identify remaining visual/cascade/interaction risks that can still make the product feel like a conventional legacy admin dashboard or cause advanced layouts to behave inconsistently.

## 2. Audit methodology

Static review was performed across templates, page CSS, shared CSS, and browser-facing JavaScript.

Checks included:

- Template inline `style` and `<style>` scan.
- JavaScript inline style/template-style/mutable-style scan.
- Cross-file CSS duplicate selector scan.
- Global selector and page CSS scope review.
- CSS metric scan for hard-coded colors, hard-coded pixel values, `!important`, fixed/sticky/overflow rules.
- Page/surface inventory review for templates that rely only on global Bootstrap-style primitives rather than the modern workspace system.
- Fixed-control / scrolling-data coverage review against actual class names used by templates and dynamic renderers.
- Load-order review for global CSS and page CSS interaction.

Runtime/browser inspection could not be completed in the sandbox because Flask is not installed locally (`ModuleNotFoundError: No module named 'flask'`).

## 3. Quantitative findings

| Area | Current finding | Risk interpretation |
| --- | ---: | --- |
| CSS files | 41 total, 40 scanned by `scripts/audit_ui_design.py` after excluding Bootstrap | Good coverage, but several global/page boundaries are blurred. |
| Template inline `style="..."`/`style='...'` attributes | 104 | Mostly runtime visibility/progress/theme swatches; the two base-page visual hits are favicon SVG stop-color attributes. |
| Template `<style>` blocks | 2 | Both are in `templates/base.html` for runtime custom CSS/theme injection and should remain controlled. |
| JavaScript inline style literals (`style="..."` / `style='...'`) | 42 | Several are dynamic/progress states, but some are still presentational. |
| JavaScript `style.cssText` uses | 5 | High-risk because it bypasses the design system and can override modern layout rules. |
| JavaScript `.style.*` mutations | 421 | Many are runtime state toggles, but some still set layout/width/z-index/visual formatting. |
| CSS `!important` declarations | 248 | Indicates cascade pressure between Bootstrap, global enterprise CSS, data-interface CSS, and page CSS. |
| CSS hard-coded hex colors | 471 | Many are fallback values, but some represent legacy color decisions outside tokens. |

## 4. Executive summary

The modern enterprise foundation is now present and broad, but several older design systems still coexist with it. The highest remaining risks are not isolated colors or small visual defects; they are architectural conflicts:

1. `styles.css` and `data-interface.css` both define broad, global versions of the same components. Because `data-interface.css` loads after page CSS, it can override page-level intent and force behavior through `!important`.
2. `static/js/responsive-fixes.js` is still an old responsive patch layer that mutates inline styles and removes duplicate pagination nodes. This directly competes with the CSS-driven fixed-control/scrolling-data model.
3. Several pages remain visibly conventional Bootstrap admin pages: concurrency dashboard, import center, basic search, entity detail pages, and some auth/user administration subareas.
4. Dynamic renderers are much cleaner than before, but some chart, path-analysis, modal, and detail modules still generate presentational inline styles or direct `style.*` layout changes.
5. The fixed-controls registry is powerful but incomplete. Some real control surfaces are not registered, and some registered selectors are broad enough that nested controls may stick unexpectedly in complex containers.

## 5. P0 / highest-priority design blockers

### P0.1 — Old responsive JavaScript still overrides modern CSS layout

**Files**

- `static/js/responsive-fixes.js`
- `static/css/responsive-fixes.css`
- `templates/base.html`

**Evidence at audit time**

`responsive-fixes.js` was loaded globally from `base.html` and performed layout mutation:

- Removed duplicate `.unified-pagination-container` and `.pagination-container` elements.
- Set `.btn-group`, `.filter-controls-grid`, `.action-bar`, `.page-header`, button widths, margins, flex directions, and grid columns through inline styles.
- Ran at DOM ready, on resize, and delayed timeouts.

**Follow-up now applied**

`responsive-fixes.js` has been rewritten as semantic responsive table metadata only. It no longer mutates visual layout styles or deletes pagination nodes; responsive layout now lives in CSS.

**Why this disrupts modern layouts**

The new design principle is that layout behavior should be owned by reusable CSS contracts (`styles.css`, `data-interface.css`, and page CSS), not by viewport-time JavaScript mutations. This legacy script can override the same surfaces that the enterprise layout depends on:

- Fixed action bars.
- Responsive filter grids.
- Page headers.
- Pagination/workbench controls.
- Button groups.

Because it writes inline styles, it beats most CSS rules and can cause unpredictable layouts after resize or after dynamic content loads.

**Recommended action**

Replace `responsive-fixes.js` with a non-visual hygiene module or remove it entirely after moving any still-needed behavior into CSS:

1. Keep only non-visual safety behavior if absolutely necessary.
2. Move responsive button/filter/header behavior into `styles.css` / `data-interface.css` media queries.
3. Remove duplicate pagination deletion and fix the rendering source instead.
4. Stop globally mutating `.filter-controls-grid`, `.action-bar`, `.page-header`, and `.btn-group`.

---

### P0.2 — Core cascade conflict between `styles.css` and `data-interface.css`

**Files**

- `static/css/styles.css`
- `static/css/data-interface.css`
- `templates/base.html`

**Evidence**

High-overlap selectors remain across both global CSS files:

- `.table-wrapper`
- `.table-responsive`
- `.file-filters-section`
- `.filter-controls-grid`
- `.search-input-wrapper`
- `.action-bar`
- `.btn-action`
- `.pagination`, `.page-link`, `.page-item`
- `.page-header`
- `.empty-state`
- `.category-card`, `.word-card`, `.id-card`

There are also 212 total `!important` declarations across non-Bootstrap CSS, with the largest counts in:

- `static/css/styles.css`: 109
- `static/css/data-interface.css`: 105

**Why this disrupts modern layouts**

`data-interface.css` is intentionally loaded after page CSS and after `styles.css`. That helps standardization, but it also means broad rules in `data-interface.css` can unexpectedly override page-specific modern layouts. Meanwhile `styles.css` also defines the same foundation components. The result is two global authorities for the same surfaces.

**Recommended action**

Create a stricter ownership model:

- `styles.css`: global shell, typography, navigation, base Bootstrap normalization, generic utilities.
- `data-interface.css`: only data workbench, table/list/grid enhancement, fixed-control/scroll-region contract.
- Page CSS: page-specific layout using namespaced classes only.

Then remove duplicated rules and reduce `!important` to accessibility/Bootstrap-normalization exceptions only.

---

### P0.3 — Fixed-control / scroll-region coverage is incomplete and can over-apply

**Files**

- `static/js/modules/core/data-interface.js`
- `static/css/data-interface.css`
- `templates/Search/search.html`
- `templates/Search/search_advanced.html`
- `templates/Search/search_enhanced.html`
- `templates/Analysis/path_analysis.html`
- `templates/file/File_Management_Analysis_System.html`

**Current registered control surfaces**

The enhancer currently marks controls such as:

- `.file-filters-section`
- `.filter-panel`, `.filters-panel`, `.advanced-filters-panel`
- `.search-command-card`, `.search-filter-section`
- `.analysis-view-navigation`
- `.analyst-classify-controls`
- `.chart-controls-wrapper`
- `.upload-controls`
- `.file-section-toolbar`
- `.action-bar`
- `.results-info-bar`
- pagination containers and paging controls

**Missing or weakly covered real control surfaces**

Classes present in templates/JS but not explicitly part of the control contract include:

- `.search-view-navigation`
- `.search-toolbar`
- `.search-toolbar-side`
- `.filters-chips-container`
- `.filter-actions-bar`
- `.results-actions`
- `.results-pagination`
- `.dashboard-navigation`
- `.tab-navigation`
- `.path-tree-actions`
- `.analyst-filters`
- `.analyst-pagination`
- `.navigation-bar`
- `.fmas-global-search-bar`
- `.sort-control`
- `.per-page-control`

**Why this disrupts modern layouts**

Some controls will stay fixed while analogous controls scroll away on another page. This is exactly the kind of inconsistency the user called out: controls should remain stable, while only data rows/results move.

**Over-application risk**

The policy currently uses broad selectors and applies sticky behavior to matched elements unless they are already inside data scroll regions. Complex nested cards/modals can still produce unexpected sticky children, especially when a result section contains nested controls or when modal content includes search/pagination controls.

**Recommended action**

1. Add an explicit semantic contract: `data-ia-role="controls"`, `data-ia-role="data-region"`, or dedicated classes such as `.ia-control-surface` and `.ia-scroll-body`.
2. Use selector-based inference only as a fallback.
3. Expand coverage for the missing classes listed above.
4. Add an opt-out attribute for nested/nonsticky controls: `data-ia-sticky="false"`.
5. Add a small DOM audit in development mode that logs unclassified control/result containers.

**Follow-up now applied**

The data-interface enhancer now recognizes explicit `data-ia-role`/`data-ia-scroll`/`data-ia-sticky` contracts, supports opt-outs, and expands fixed-control/data-region coverage for the missing search, FMAS, dashboard, path-analysis, analyst, chart, and pagination classes.

---

### P0.4 — `charts-dashboard-page.js` still contains old inline empty-state rendering

**Files**

- `static/js/pages/charts-dashboard-page.js`
- `static/css/charts-dashboard.css`
- `static/css/comprehensive-dashboard.css`

**Evidence at audit time**

`charts-dashboard-page.js` still created an empty state with `style.cssText` and inline icon/text styles, while `comprehensive-dashboard-page.js` had already been normalized to `.chart-empty-state`.

**Follow-up now applied**

`charts-dashboard-page.js` now uses the shared `.chart-empty-state` surface, and the shared chart empty-state styling lives in `static/css/chart-export.css`.

**Why this disrupts modern layouts**

Two dashboard chart surfaces can display analogous empty states differently. This also bypasses density/theme tokens and can ignore the fixed-control/scroll-body contract.

**Recommended action**

Move `charts-dashboard-page.js` to the same `chart-empty-state` class contract used by the comprehensive dashboard and define the shared rule in a chart-wide stylesheet rather than separately per page.

## 6. P1 / major remaining outdated surfaces

### P1.1 — Concurrency dashboard is still a legacy Bootstrap admin screen

**Files**

- `templates/concurrency/dashboard.html`
- `static/js/pages/concurrency-dashboard-page.js`

**Evidence**

- Uses plain `.card`, `.card-body`, `.card-header`, `.nav-tabs` without a dedicated modern page CSS layer.
- Uses Bootstrap 4 `data-toggle="tab"` instead of Bootstrap 5 `data-bs-toggle="tab"` while the app loads Bootstrap 5 bundle.
- Polls every 2 seconds and rewrites manager cards and detailed tables using `innerHTML`.
- Generated tables have only `.table .table-sm`; no title/data attributes, no stable table workbench metadata, no dedicated empty/loading classes.
- Labels are hard-coded English in JS (`Status`, `Active`, `Completed`, `Errors`, etc.).

**Impact**

This page will feel older than the rest of the platform and can behave incorrectly due to Bootstrap version mismatch. The frequent full re-render also undermines polished micro-interactions and can fight the data-interface enhancer.

**Recommended action**

Rebuild as an enterprise operations workspace:

- Use `section-card`, `ia-record-list`, and enhanced table wrappers.
- Replace Bootstrap 4 tab attributes.
- Update DOM incrementally instead of rebuilding entire table/card HTML every poll.
- Add fixed controls for refresh/range/filter, and make only table bodies scroll.
- Add i18n strings and modern empty/loading states.

**Follow-up now applied**

The concurrency dashboard now has a dedicated enterprise workspace shell, stable refresh/status controls, compact manager metric strip, Bootstrap 5 tab triggers, scroll-contained detail tables, translated label configuration, and DOM-based incremental row/metric rendering with hidden-tab polling suppression.

---

### P1.2 — Import Center remains a Bootstrap utility page with inline script

**Files**

- `templates/Operations/import_center.html`

**Evidence**

- Uses `.container-fluid py-4`, `.card shadow-sm`, `.bg-light`, `.border rounded`, generic Bootstrap utilities.
- Contains substantial inline JavaScript inside the template.
- No page-specific CSS file or enterprise workbench structure.
- Action controls are inside cards rather than a stable, reusable import workbench.

**Impact**

The import workflow looks and behaves differently from the modern ingestion/operations patterns. Inline JavaScript also makes it harder to standardize loading, errors, fixed controls, and result scroll regions.

**Recommended action**

Extract JS into `static/js/pages/import-center-page.js`, add `static/css/import-center.css` or fold into operations styles, and convert the page to a fixed import workbench with scrollable validation/preview results.

**Follow-up now applied**

The Import Center now uses a dedicated operations workbench layout, source-specific compact panels, stable preview/confirmation controls, scroll-contained validation output, externalized page JavaScript, DOM-safe preview/message rendering, and metadata-driven labels/CSRF handling.

---

### P1.3 — Basic search page still competes with advanced/enhanced search UI

**Files**

- `templates/Search/search.html`
- `static/js/pages/search-page.js`
- `static/css/search-advanced.css`
- `static/css/search-enhanced.css`

**Evidence**

- Basic search uses a conventional `.section-card` form plus Bootstrap rows/cards.
- It duplicates advanced search options already found elsewhere.
- Results are rendered as `.list-group` entries rather than the newer dense result cards.
- Dynamic pagination is rendered manually with inline `onclick` handlers and no unified pagination component.
- No dedicated `search.css`; it relies on globals and advanced/enhanced CSS only where those templates load them.

**Impact**

Three search experiences exist visually and structurally: basic, advanced, and enhanced. This weakens the sense of one coherent intelligence workspace.

**Recommended action**

Unify search navigation and result rendering behind one search workspace shell. Use the advanced/enhanced result card pattern for basic search and route all pagination through the unified pagination renderer.

---

### P1.4 — Entity detail pages still use older sparse admin layouts

**Files**

- `templates/Sources/source_detail.html`
- `templates/Side/side_detail.html`
- `templates/Keyword/keyword_detail.html`
- `templates/Word/Word_detail.html`
- `static/js/pages/source-detail-page.js`
- `static/js/pages/side-detail-page.js`
- `static/js/pages/word-detail-page.js`
- `static/js/pages/keyword-detail-page.js`

**Evidence**

- Source/side detail pages use repeated `text-center p-3 bg-light rounded` stat boxes.
- Actions are simple Bootstrap buttons, not contextual enterprise action bars.
- Detail pages rely primarily on Bootstrap row/column layouts, not a master/detail workspace.
- `source-detail-page.js` and `word-detail-page.js` still contain TODO comments about copying inline JavaScript from templates.
- Delete flows still use browser `confirm()`/`alert()` fallbacks in several detail modules.

**Impact**

Users moving from dense list/workbench pages to detail pages experience a design downgrade. These pages also miss opportunities for related records, fixed detail actions, keyboard shortcuts, and consistent advanced empty/loading/error states.

**Recommended action**

Create a reusable entity detail shell:

- Summary metric strip.
- Sticky contextual action bar.
- Relationship/data panels with enhanced tables or record lists.
- Consistent delete/confirm modal pattern.
- Master/detail navigation back to sources/sides/words/keywords.

---

### P1.5 — User administration is mostly functional but not fully enterprise-aligned

**Files**

- `templates/auth/users.html`
- `static/js/pages/users-page.js`

**Evidence**

- The users table is enhanced by global behavior, but role capability matrix remains a static Bootstrap table.
- Account actions are row-level Bootstrap buttons only; no bulk actions, saved views, or advanced filters.
- Create/delete/reset modals use standard Bootstrap modal shells.

**Impact**

It is acceptable functionally, but it does not match the advanced data-analysis treatment of other entity lists.

**Recommended action**

Promote Users to the data-interface workbench pattern: filters for role/status, saved views, row selection, bulk activation/deactivation where permissions allow, and enterprise modal states.

**Follow-up now applied**

User administration now uses a dedicated governance workspace shell, stable search/role/status filters, an enhanced accounts table region, a compact capability workbench, DOM-safe row rendering, delegated row actions, translated labels, and the shared confirmation/message system where available.

## 7. P1 / design-system and CSS architecture issues

### P1.6 — Global chart styles are scattered and sometimes globally loaded

**Files**

- `static/css/chart-export.css`
- `static/css/charts-dashboard.css`
- `static/css/comprehensive-dashboard.css`
- `static/css/dashboard.css`
- `templates/base.html`
- `static/js/modules/charts/*`

**Evidence**

`chart-export.css` is globally loaded from `base.html`, while chart containers are also styled in dashboard-specific CSS files. Duplicate selectors include:

- `.chart-container`
- `.chart-container-layout`
- `.chart-actions`
- `.chart-toolbar`
- `.chart-card`

**Impact**

Chart pages can inherit export styles globally, and non-chart pages pay cascade overhead. Similar chart cards can differ between dashboard, comprehensive dashboard, and chart dashboard.

**Recommended action**

Create a single chart-workspace layer for shared chart layout and load export styles only where chart export UI exists, or namespace global chart export selectors under `.chart-export-*` only.

---

### P1.7 — Generic class names in page CSS can leak across pages

**Files / examples**

- `static/css/categories-list.css`: `.category-card`
- `static/css/category-words.css`: `.word-card`
- `static/css/file-manger.css`: `.file-card`
- `static/css/fmas.css`: `.section`, `.section-header`, `.file-card-icon`, `.file-card-actions`
- `static/css/path-analysis.css`: `.file-card`, `.chart-loading-overlay`, `.modal-file-*`
- `static/css/search-advanced.css`: `.result-card`, `.results-header`, `.filter-label`
- `static/css/search-enhanced.css`: `.filter-section`, `.result-item`

**Impact**

When generic page CSS is loaded alongside shared CSS or reused in another template, analogous records can acquire styles from the wrong page. This is one cause of inconsistent “same component, different visual treatment” behavior.

**Recommended action**

Namespace page-owned classes:

- `.source-card` / `.sources-card` rather than `.category-card` where possible.
- `.path-file-card` rather than `.file-card` on path analysis.
- `.search-result-card` rather than `.result-card`.
- Keep reusable primitives in `styles.css` or `data-interface.css` only.

---

### P1.8 — `auth-workspace.css` is standalone but contains broad global selectors

**Files**

- `static/css/auth-workspace.css`
- `templates/auth/login.html`
- `templates/auth/first_admin.html`
- `templates/Setup/install_wizard.html`

**Evidence**

The stylesheet contains broad selectors such as:

- `*`, `*::before`, `*::after`
- `body`
- `.form-control`
- `.alert`, `.alert-danger`, `.alert-success`, `.alert-warning`
- `.card-body`, `.field-label`, `.form-text`

**Impact**

It is currently safe because it is loaded by standalone auth/setup pages, not by `base.html`. If it is ever loaded into the main app shell, it will compete with the enterprise global design system.

**Recommended action**

Wrap standalone styles under an auth root class, such as `.auth-workspace`, and avoid broad Bootstrap overrides outside that namespace.

## 8. P2 / medium-priority cleanup issues

### P2.1 — Remaining inline template styles need formal classification

Most template inline styles are runtime state or user-configurable theme previews, but they should be explicitly governed.

**Primary files**

- `templates/Settings/settings.html`: 51 inline style attributes, mostly display toggles and theme color swatches.
- `templates/file/File_Management_Analysis_System.html`: 10 inline display toggles.
- `templates/Search/search_advanced.html`: 5 inline display toggles.
- `templates/ImportExport/import_export.html`: display toggles and progress width.
- `templates/Analysis/analysis_batch.html`: progress display/width.
- `templates/base.html`: dynamic app icon visibility/password mismatch display plus runtime style tags.

**Recommended action**

Create a policy:

Allowed inline styles:

- Dynamic progress width.
- User-selected theme color preview swatches.
- Runtime `display:none` boot state when server-rendered markup must avoid flicker.

Not allowed:

- Static spacing, color, border, shadow, font, layout, or animation.

Then enforce via a lint script that reports new non-allowed inline styles.

---

### P2.2 — JavaScript still contains presentational style mutations

Many `.style.*` changes are legitimate runtime toggles, but the current number is high enough to hide regressions.

**Higher-risk files**

- `static/js/responsive-fixes.js`: layout mutations; should be removed or converted to CSS.
- `static/js/pages/charts-dashboard-page.js`: inline empty state styles.
- `static/js/modules/charts/classification-charts.js`: inline `cssText` for empty states.
- `static/js/modules/core/loading-manager.js`: inline loading overlay styles.
- `static/js/modules/charts/chart-customizer.js`: inline control-wrapper styles.
- `static/js/pages/keywords-list-page.js`: one remaining visual left-border style on rows.
- `static/js/modules/file-operations/file-details.js`: dynamic lineage indentation via inline margin.

**Recommended action**

Introduce helper classes and data attributes:

- Toggle classes instead of setting visual properties.
- Use CSS custom properties only for truly dynamic values, e.g. `--progress-width`, `--lineage-depth`, `--chart-height`.
- Keep direct style mutation only for progress width and canvas/chart library requirements.

---

### P2.3 — Old fallback renderers and compatibility comments remain

**Examples**

- `static/js/pages/words-list-page.js`: fallback old pagination renderer.
- `static/js/pages/keywords-list-page.js`: fallback old pagination renderer and checks for old pagination containers.
- `static/js/pages/source-categories-keywords-page.js` and `static/js/pages/side-categories-keywords-page.js`: fallback to old pagination.
- `static/js/translations-loader.js`, `static/js/pages/data-helper.js`, and several modules expose globals for backward compatibility.

**Impact**

Compatibility paths can reintroduce older visual patterns when modern modules fail or load late.

**Recommended action**

Audit fallback paths and either:

- Make the fallback produce the same modern classes/components, or
- Remove the fallback once the modern dependency is guaranteed.

---

### P2.4 — Hard-coded theme colors still appear as fallbacks or direct values

**Examples**

- `static/css/data-interface.css` contains many fallback colors for tokens.
- `static/css/styles.css` contains direct values for some Bootstrap normalization, including secondary buttons.
- `static/css/auth-workspace.css` contains many standalone theme colors.
- `static/js/settings/settings-ui.js` and `static/js/modules/ui/theme-manager.js` contain default color maps.

**Impact**

Fallback values are not inherently wrong, but excessive hard-coded values make it hard to guarantee professional light/dark theme polish.

**Recommended action**

Centralize default token values in one source of truth and make CSS/JS consume that map consistently. Keep fallbacks only where necessary for standalone pages or first-paint safety.

---

### P2.5 — Some scripts still use browser `alert()` / `confirm()` instead of the enterprise modal/message system

**Files / examples**

- `static/js/pages/source-detail-page.js`
- `static/js/pages/side-detail-page.js`
- `static/js/pages/word-detail-page.js`
- `static/js/pages/search-page.js`
- `static/js/pages/email-words-page.js`
- `static/js/pages/file-classification-page.js`

**Impact**

Native browser dialogs feel dated and break the polished workflow model.

**Recommended action**

Use the existing message/modal system for confirmations and errors, with native dialogs only as emergency fallbacks.

## 9. Fixed-controls audit matrix

| Surface | Current condition | Risk | Recommendation |
| --- | --- | --- | --- |
| Table workbenches | Strong global enhancement exists. | Broad CSS overlap may override page-specific controls. | Keep in `data-interface.css`, reduce duplicate table rules in `styles.css`. |
| File/list filters | Covered by `.file-filters-section`. | `responsive-fixes.js` can override columns/widths inline. | Remove JS layout mutation. |
| Search navigation | `.search-view-navigation` not in control registry. | Search view tabs can scroll differently from other navigation controls. | Add to explicit fixed controls. |
| Advanced search chips/actions | `.filters-chips-container`, `.filter-actions-bar`, `.results-actions`, `.results-pagination` not fully registered. | Filter chips/action bars may scroll away. | Add semantic control classes or data roles. |
| Path tree controls | `.path-tree-actions` not registered. | Tree controls can move while tree data scrolls. | Mark controls fixed; mark tree/list regions scrollable. |
| FMAS controls | `.file-section-toolbar` covered, but `.fmas-global-search-bar`, `.sort-control`, `.per-page-control`, `.navigation-bar` are not all covered. | Similar FMAS controls can behave differently. | Add explicit control class or registry entries. |
| Modal search/results | Modal max-height exists; display states are still inline. | Nested sticky controls may conflict in modal content. | Add modal-specific control/data roles and opt-outs. |
| Pagination | Covered by several selectors. | Old pagination fallback and duplicate deletion remain. | Standardize all pagination through unified renderer. |

## 10. Page/surface modernization inventory

| Page/surface | Status | Main remaining modernization gap |
| --- | --- | --- |
| Sources list | Modernized | Ensure detail page matches list quality. |
| Sides list | Modernized | Ensure detail page matches list quality. |
| Words list | Mostly modernized | Old pagination fallback remains. |
| Keywords list | Mostly modernized | Old pagination fallback and minor visual style mutation remain. |
| Categories / category words | Mostly modernized | Class namespace remains generic; fallback states need governance. |
| FMAS / archive explorer | Substantially modernized | Control registry should explicitly cover all toolbars/search/sort/per-page controls. |
| File detail/full content | Mostly modernized | Some JS-driven layout and lineage indentation remain. |
| Search advanced/enhanced | Modern direction present | Basic search and shared search shell are not unified. |
| Basic search | Legacy leaning | Convert to shared search workspace/result renderer. |
| Dashboard / comprehensive dashboard | Mostly modernized | Chart dashboard still has old inline empty states; chart styles are scattered. |
| Charts dashboard | Partially modernized | Normalize empty/loading states and chart layout with comprehensive dashboard. |
| Path analysis | Mostly modernized | Dynamic chart/canvas sizing and progress widths remain; acceptable if governed with CSS variables. |
| File classification | Modernized structurally | Native alerts and direct display mutations remain. |
| Upload/chunked upload | Modernized structurally | Progress widths and hidden file input are expected; ensure controls fixed. |
| Operations jobs/detail/input | Modernized through global helpers | Import center is not modernized. |
| Import center | Legacy leaning | Needs extracted JS, page CSS, fixed action/results workbench. |
| Notifications | Mostly modernized | Verify detail modal scroll/fixed action behavior in browser. |
| Settings | Mostly modernized | Many inline dynamic swatches/display states; needs lint allowlist. |
| Auth/login/first-admin/setup | Modern standalone | Namespace `auth-workspace.css` to prevent future leakage. |
| User management | Functional | Add advanced filters/bulk/saved views to match enterprise workspace. |
| Concurrency dashboard | Legacy | Needs full enterprise rebuild and Bootstrap 5 tab fix. |
| Entity detail pages | Legacy leaning | Need reusable master/detail/entity-detail shell. |

## 11. Recommended remediation plan

### Phase 1 — Stop active layout interference

1. Remove or rewrite `static/js/responsive-fixes.js` so it no longer writes layout styles.
2. Fix any duplicate pagination at the renderer/source level.
3. Move responsive behavior into CSS media queries.
4. Normalize `charts-dashboard-page.js` empty states to `.chart-empty-state`.
5. Expand fixed-control registry or add semantic `data-ia-role` attributes for missing controls.

### Phase 2 — Clarify CSS ownership and remove duplicate global authority

1. Define ownership boundaries for `styles.css`, `data-interface.css`, page CSS, and standalone CSS.
2. Deduplicate shared selectors, especially table/filter/action/pagination/card/result components.
3. Reduce `!important` usage by ordering and specificity rather than force.
4. Namespace page CSS that currently uses generic classes.

### Phase 3 — Modernize remaining legacy pages

1. Rebuild Concurrency dashboard.
2. Rebuild Import Center.
3. Unify Basic Search with the advanced/enhanced search workspace.
4. Create reusable entity detail shell for source/side/word/keyword/detail pages.
5. Upgrade User Management to the same enterprise workbench pattern as entity lists.

### Phase 4 — Add design regression governance

1. Use `scripts/audit_ui_design.py` to report inline styles, JS style mutation, CSS duplicate selectors, broad page selectors, hard-coded colors and `!important` counts.
2. Add stricter fail-on-new thresholds once the current backlog is burned down.
3. Add a dev-only DOM audit that logs unclassified control/data regions.
4. Add visual smoke coverage once Flask/test browser dependencies are available.
5. Document allowed runtime styles: progress width, theme swatches, canvas sizing, file input hiding, and initial no-flicker display states.

## 12. Suggested acceptance criteria for the next cleanup pass

- No global JavaScript mutates layout dimensions/flex/grid styles for responsive behavior.
- All control surfaces on search, file, analysis, operations, and entity pages are fixed/stable while only data regions scroll.
- No page CSS defines un-namespaced reusable component classes unless that class is owned by the shared design system.
- Basic search, advanced search, and enhanced search share one navigation/results/action model.
- Concurrency dashboard and Import Center no longer look like standalone Bootstrap admin screens.
- Entity detail pages use a consistent master/detail shell with contextual actions and related data panels.
- New inline styles fail lint unless explicitly allowlisted as runtime/dynamic values.
- Browser validation confirms sticky controls do not over-stick inside modals or nested result sections.

## 13. Known non-issues / intentionally retained patterns

These patterns should not be removed blindly:

- `templates/base.html` runtime custom CSS/style blocks for user settings and first-paint theme variables.
- Dynamic progress widths (`style="width: ...%"`) where the value is data-driven.
- Theme color swatch backgrounds in Settings.
- Hidden file inputs and initial `display:none` states that prevent flicker before JavaScript activates.
- Chart/canvas sizing that must be calculated from data or viewport, provided it uses CSS variables/classes where possible.

## 14. Bottom line

The enterprise redesign foundation is substantially in place, but the remaining outdated design risks are concentrated in a few systemic areas: global responsive JavaScript, duplicated global CSS ownership, incomplete fixed-control classification, scattered chart styling, and a handful of still-legacy pages. Addressing those areas will remove the main sources of disruption and make the platform feel consistently modern, dense, and professional across every workflow.
