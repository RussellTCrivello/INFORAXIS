/**
 * Analyst classification from any content display interface.
 *
 * Shared by the File Detail page and the Full Content Reader. Lets an
 * analyst/admin assign or remove ANALYST (manual) categories for the file
 * they are currently reading — without going back to Advanced Search or
 * the Analyst View.
 *
 * All writes go through the existing, audit-logged endpoints:
 *   GET    /api/analyst/categories      — list analyst categories
 *   POST   /api/analyst/assign          — {path_ids, category_id | category_name, source_query}
 *   POST   /api/analyst/remove          — {path_ids}
 * (FR-1.4: analyst namespace only; the smart taxonomy is never touched.)
 *
 * The module self-initializes when a #analystClassifyCard element exists
 * on the page. Page-data translations come from the nearest
 * #analyst-classify-page-data JSON block (same pattern as the other page
 * scripts).
 */

let t = null;
let fileId = null;
let cardEl = null;

function classifyT(key, fallback) {
    return (t && t[key]) ? t[key] : fallback;
}

function csrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
}

async function apiPost(url, payload) {
    const res = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken(),
        },
        body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.success === false) {
        throw new Error(data.error || `HTTP ${res.status}`);
    }
    return data;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = String(text == null ? '' : text);
    return div.innerHTML;
}

let toastTimer = null;
function showToast(message, isError = false) {
    let toast = document.getElementById('analystClassifyToast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'analystClassifyToast';
        toast.className = 'analyst-action-toast';
        document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.classList.toggle('toast-error', isError);
    toast.classList.add('visible');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('visible'), 3200);
}

/** Re-render the badge list from a categories array [{id, name}]. */
function renderBadges(categories) {
    const wrap = document.getElementById('analystClassifyBadges');
    if (!wrap) return;
    const canCategorize = !!cardEl.dataset.canCategorize;
    if (!categories || !categories.length) {
        wrap.innerHTML = `<span class="analyst-classify-empty" id="analystClassifyEmpty">${escapeHtml(classifyT('noCategoriesYet', 'No analyst categories yet.'))}</span>`;
        return;
    }
    wrap.innerHTML = categories.map(cat => `
        <span class="badge analyst-category-badge" data-category-id="${cat.id}">
            <i class="bi bi-person-fill me-1" aria-hidden="true"></i>${escapeHtml(cat.name)}
            ${canCategorize ? `
            <button type="button" class="badge-remove" data-remove-category-id="${cat.id}"
                    title="${escapeHtml(classifyT('confirmRemove', 'Remove analyst category from this file? It returns to uncategorized status for search scope.'))}"
                    aria-label="${escapeHtml(classifyT('removeLabel', 'Remove'))} ${escapeHtml(cat.name)}">&times;</button>` : ''}
        </span>`).join('');
}

/** Authoritative refresh: exact per-file assignments via the file_id
 *  filter (the same source the Analyst View uses). */
async function reloadCurrentCategories() {
    try {
        const res = await fetch(`/api/analyst/assignments?file_id=${fileId}&per_page=100`);
        if (!res.ok) return;
        const data = await res.json();
        const rows = data.assignments || [];
        const seen = new Map();
        rows.forEach(r => seen.set(r.category_id, r.category_name));
        renderBadges([...seen.entries()].map(([id, name]) => ({ id, name })));
    } catch (e) {
        console.error('analyst-classify: refresh failed', e);
    }
}

async function loadCategoryOptions() {
    const select = document.getElementById('analystClassifySelect');
    if (!select) return;
    try {
        const res = await fetch('/api/analyst/categories');
        if (!res.ok) return;
        const categories = await res.json();
        if (!Array.isArray(categories)) return;
        select.innerHTML = '<option value="">' +
            escapeHtml(classifyT('chooseCategory', 'Choose analyst category…')) + '</option>' +
            categories.map(c =>
                `<option value="${c.id}">${escapeHtml(c.name)} (${c.file_count ?? 0})</option>`
            ).join('');
    } catch (e) {
        console.error('analyst-classify: could not load categories', e);
    }
}

async function assign() {
    const select = document.getElementById('analystClassifySelect');
    const newName = document.getElementById('analystClassifyNewName');
    const categoryId = select && select.value ? parseInt(select.value, 10) : null;
    const categoryName = newName && newName.value.trim() ? newName.value.trim() : null;

    if (!categoryId && !categoryName) {
        showToast(classifyT('chooseOrCreateCategory', 'Choose an analyst category or type a new one'), true);
        return;
    }

    const payload = {
        path_ids: [Number(fileId)],
        source_query: classifyT('sourceContext', 'content view'),
        create_category: !categoryId && !!categoryName,
    };
    if (categoryId) payload.category_id = categoryId;
    if (categoryName) payload.category_name = categoryName;

    try {
        const data = await apiPost('/api/analyst/assign', payload);
        if (newName) newName.value = '';
        if (select) select.value = '';
        showToast(
            classifyT('assignedToast', 'Assigned "{category}" to {count} file(s)')
                .replace('{category}', data.category_name || categoryName || '')
                .replace('{count}', String(data.assigned ?? 1))
        );
        await reloadCurrentCategories();
    } catch (e) {
        showToast(classifyT('assignFailed', 'Analyst categorization failed') + ': ' + e.message, true);
    }
}

async function removeAll() {
    if (!window.confirm(
        classifyT('removeAllConfirmFile', 'Remove all analyst categories from this file? It will return to "uncategorized" for analyst search scope. Smart categories are not affected.')
    )) return;
    try {
        const data = await apiPost('/api/analyst/remove', { path_ids: [Number(fileId)] });
        showToast(
            classifyT('removedToast', 'Removed analyst categories from {count} file(s)')
                .replace('{count}', String(data.removed_assignments ?? 1))
        );
        await reloadCurrentCategories();
    } catch (e) {
        showToast(classifyT('removeFailed', 'Remove failed') + ': ' + e.message, true);
    }
}

async function removeOne(categoryId) {
    if (!window.confirm(
        classifyT('confirmRemove', 'Remove analyst category from this file? It returns to uncategorized status for search scope.')
    )) return;
    // The remove endpoint removes ALL analyst categories for given paths
    // (bulk semantics), so single-category removal = remove all + reassign
    // the remaining ones. Simplest correct sequence:
    try {
        const badges = [...document.querySelectorAll('#analystClassifyBadges .badge[data-category-id]')];
        const remaining = badges
            .map(b => parseInt(b.dataset.categoryId, 10))
            .filter(id => id !== Number(categoryId));
        await apiPost('/api/analyst/remove', { path_ids: [Number(fileId)] });
        for (const catId of remaining) {
            await apiPost('/api/analyst/assign', {
                path_ids: [Number(fileId)],
                category_id: catId,
                source_query: classifyT('sourceContext', 'content view'),
            });
        }
        showToast(classifyT('categoryRemoved', 'Analyst category removed'));
        await reloadCurrentCategories();
    } catch (e) {
        showToast(classifyT('removeFailed', 'Remove failed') + ': ' + e.message, true);
    }
}

function init() {
    cardEl = document.getElementById('analystClassifyCard');
    if (!cardEl) return;

    const dataEl = document.getElementById('analyst-classify-page-data');
    if (dataEl) {
        try {
            const data = JSON.parse(dataEl.textContent);
            t = data.translations || {};
            cardEl.dataset.canCategorize = data.canCategorize ? 'true' : 'false';
        } catch (e) { /* fall back to defaults */ }
    }

    fileId = cardEl.dataset.fileId;

    const assignBtn = document.getElementById('analystClassifyAssignBtn');
    if (assignBtn) assignBtn.addEventListener('click', assign);
    const removeAllBtn = document.getElementById('analystClassifyRemoveAllBtn');
    if (removeAllBtn) removeAllBtn.addEventListener('click', removeAll);
    const newName = document.getElementById('analystClassifyNewName');
    if (newName) newName.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); assign(); } });

    // Per-badge removal (event delegation — badges are re-rendered)
    const badgesEl = document.getElementById('analystClassifyBadges');
    if (badgesEl) {
        badgesEl.addEventListener('click', e => {
            const btn = e.target.closest('[data-remove-category-id]');
            if (btn) removeOne(btn.dataset.removeCategoryId);
        });
    }

    loadCategoryOptions();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}

window.analystClassify = { refreshState: reloadCurrentCategories, reloadCurrentCategories };
