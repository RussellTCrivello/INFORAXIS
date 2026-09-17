/**
 * User Management page (/users, admin-only).
 * Enterprise admin workbench with stable filters and DOM-safe row rendering.
 */

let translations = {};
let currentUserId = null;
let allUsers = [];

function getCSRFToken() {
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    return metaTag ? metaTag.getAttribute('content') : '';
}

function t(key, fallback) {
    return translations[key] || fallback;
}

function notify(message, type = 'error') {
    if (type === 'success' && window.showSuccess) {
        window.showSuccess(message);
        return;
    }
    if (type === 'error' && window.showError) {
        window.showError(message);
        return;
    }
    console[type === 'error' ? 'error' : 'log'](message);
}

async function confirmAction(message, options = {}) {
    if (window.showConfirm) return window.showConfirm(message, options);
    const originalConfirm = window.__originalConfirm || window.confirm;
    return originalConfirm(message);
}

function textCell(value, className = '') {
    const td = document.createElement('td');
    if (className) td.className = className;
    td.textContent = value == null || value === '' ? '—' : String(value);
    return td;
}

function pill(text, className, data = {}) {
    const span = document.createElement('span');
    span.className = className;
    span.textContent = text;
    Object.entries(data).forEach(([key, value]) => {
        span.dataset[key] = value;
    });
    return span;
}

function button(label, icon, className, action, userId, title = '') {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = className;
    btn.dataset.userAction = action;
    btn.dataset.userId = userId;
    if (title) btn.title = title;

    const iconEl = document.createElement('i');
    iconEl.className = icon;
    iconEl.setAttribute('aria-hidden', 'true');
    btn.append(iconEl);
    if (label) {
        const text = document.createElement('span');
        text.textContent = label;
        btn.append(document.createTextNode(' '), text);
    }
    return btn;
}

function roleLabel(role) {
    if (role === 'admin') return t('admin', 'Admin');
    if (role === 'analyst') return t('analyst', 'Analyst');
    if (role === 'viewer') return t('viewer', 'Viewer');
    return role || t('unknownError', 'Unknown');
}

function renderRoleSelect(user) {
    const select = document.createElement('select');
    select.className = 'form-select form-select-sm user-role-select';
    select.dataset.userId = user.id;
    select.setAttribute('aria-label', `${t('roleFor', 'Role for')} ${user.username}`);
    ['viewer', 'analyst', 'admin'].forEach((role) => {
        const option = document.createElement('option');
        option.value = role;
        option.textContent = roleLabel(role);
        option.selected = role === user.role;
        select.append(option);
    });
    return select;
}

function renderActiveToggle(user, isSelf) {
    const wrapper = document.createElement('div');
    wrapper.className = 'form-check form-switch m-0';

    const input = document.createElement('input');
    input.className = 'form-check-input user-active-toggle';
    input.type = 'checkbox';
    input.role = 'switch';
    input.checked = !!user.is_active;
    input.disabled = isSelf;
    input.dataset.userId = user.id;
    input.setAttribute('aria-label', `${t('activeStatusFor', 'Active status for')} ${user.username}`);

    wrapper.append(input);
    return wrapper;
}

function createUserRow(user) {
    const isSelf = user.id === currentUserId;
    const tr = document.createElement('tr');
    tr.dataset.userId = user.id;

    tr.append(textCell(user.id));

    const nameCell = document.createElement('td');
    const nameStack = document.createElement('div');
    nameStack.className = 'users-name-stack';
    const username = document.createElement('strong');
    username.textContent = user.username || '—';
    nameStack.append(username);
    if (isSelf) nameStack.append(pill(t('you', 'You'), 'users-self-pill'));
    if (user.must_change_password) nameStack.append(pill(t('temporaryPassword', 'temp pw'), 'users-temp-pill'));
    nameCell.append(nameStack);
    tr.append(nameCell);

    const roleCell = document.createElement('td');
    if (isSelf) {
        roleCell.append(pill(roleLabel(user.role), 'users-role-badge', { role: user.role || 'viewer' }));
    } else {
        roleCell.append(renderRoleSelect(user));
    }
    tr.append(roleCell);

    const statusCell = document.createElement('td');
    statusCell.append(renderActiveToggle(user, isSelf));
    statusCell.append(pill(user.is_active ? t('active', 'Active') : t('inactive', 'Inactive'), 'users-status-pill ms-2', { status: user.is_active ? 'active' : 'inactive' }));
    tr.append(statusCell);

    tr.append(textCell(user.created_at ? String(user.created_at).slice(0, 10) : '—'));

    const actionCell = document.createElement('td');
    actionCell.className = 'text-end';
    const actions = document.createElement('div');
    actions.className = 'users-row-actions';
    actions.append(button(t('resetPassword', 'Reset PW'), 'bi bi-key', 'btn btn-sm btn-outline-warning', 'reset', user.id, t('confirmReset', 'Generate a new temporary password for this user?')));
    if (!isSelf) {
        actions.append(button('', 'bi bi-trash', 'btn btn-sm btn-outline-danger', 'delete', user.id, t('deleteUser', 'Delete user')));
    }
    actionCell.append(actions);
    tr.append(actionCell);

    return tr;
}

function renderEmptyRow(message, isError = false) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 6;
    td.className = `text-center py-4 ${isError ? 'text-danger' : 'text-muted'}`;
    td.textContent = message;
    tr.append(td);
    return tr;
}

function setUsersCount(filteredCount) {
    const countEl = document.getElementById('usersCount');
    if (!countEl) return;
    countEl.textContent = filteredCount === allUsers.length ? String(allUsers.length) : `${filteredCount}/${allUsers.length}`;
}

function filteredUsers() {
    const query = (document.getElementById('userSearchFilter')?.value || '').trim().toLowerCase();
    const role = document.getElementById('userRoleFilter')?.value || 'all';
    const status = document.getElementById('userStatusFilter')?.value || 'all';

    return allUsers.filter((user) => {
        const matchesQuery = !query || [user.username, user.role, user.id].some((value) => String(value || '').toLowerCase().includes(query));
        const matchesRole = role === 'all' || user.role === role;
        const matchesStatus = status === 'all'
            || (status === 'active' && user.is_active)
            || (status === 'inactive' && !user.is_active)
            || (status === 'temporary' && user.must_change_password);
        return matchesQuery && matchesRole && matchesStatus;
    });
}

function renderUsers(users) {
    const tbody = document.getElementById('usersTableBody');
    if (!tbody) return;
    const fragment = document.createDocumentFragment();
    if (!users.length) {
        fragment.append(renderEmptyRow(t('noUsers', 'No users found.')));
    } else {
        users.forEach((user) => fragment.append(createUserRow(user)));
    }
    tbody.replaceChildren(fragment);
    setUsersCount(users.length);
    window.InforaxisDataInterface?.refresh?.(document.getElementById('usersTable'));
}

function applyUserFilters() {
    renderUsers(filteredUsers());
}

async function loadUsers() {
    const tbody = document.getElementById('usersTableBody');
    if (!tbody) return;
    try {
        const response = await fetch('/api/auth/users', {
            headers: { Accept: 'application/json', 'X-CSRFToken': getCSRFToken() }
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        allUsers = Array.isArray(data.users) ? data.users : [];
        applyUserFilters();
    } catch (error) {
        tbody.replaceChildren(renderEmptyRow(`${t('error', 'Error')}: ${error.message}`, true));
    }
}

async function updateUser(userId) {
    const row = document.querySelector(`tr[data-user-id="${userId}"]`);
    if (!row) return;
    const role = row.querySelector('.user-role-select')?.value;
    const isActive = row.querySelector('.user-active-toggle')?.checked;

    if (userId === currentUserId) {
        notify(t('cannotChangeSelf', 'You cannot change your own role or status.'), 'error');
        loadUsers();
        return;
    }

    const body = {};
    if (role) body.role = role;
    if (typeof isActive === 'boolean') body.is_active = isActive;

    const response = await fetch(`/api/auth/users/${userId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken() },
        body: JSON.stringify(body)
    });
    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        notify(`${t('error', 'Error')}: ${err.error || t('unknownError', 'Unknown error')}`, 'error');
    }
    loadUsers();
}

async function resetPassword(userId) {
    const confirmed = await confirmAction(t('confirmReset', 'Generate a new temporary password for this user? Their current sessions will be revoked.'), {
        title: t('resetPassword', 'Reset PW'),
        confirmLabel: t('resetPassword', 'Reset PW'),
        type: 'warning'
    });
    if (!confirmed) return;

    const response = await fetch(`/api/auth/users/${userId}/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken() }
    });
    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        notify(`${t('error', 'Error')}: ${err.error || t('unknownError', 'Unknown error')}`, 'error');
        return;
    }
    const data = await response.json();
    const valueEl = document.getElementById('resetPasswordValue');
    if (valueEl && data.temporary_password) {
        valueEl.value = data.temporary_password;
        const modal = new bootstrap.Modal(document.getElementById('resetPasswordModal'));
        modal.show();
    }
    loadUsers();
}

function showDeleteUserModal(userId, username) {
    const modalEl = document.getElementById('deleteUserModal');
    if (!modalEl) return;
    document.getElementById('deleteUserModalName').textContent = username;
    const confirmBtn = document.getElementById('deleteUserConfirm');
    confirmBtn.dataset.userId = userId;
    const modal = new bootstrap.Modal(modalEl);
    modal.show();
    setTimeout(() => confirmBtn.focus(), 300);
}

async function deleteUser(userId) {
    const confirmBtn = document.getElementById('deleteUserConfirm');
    const errorBox = document.getElementById('deleteUserError');
    errorBox.classList.add('d-none');
    confirmBtn.disabled = true;
    try {
        const response = await fetch(`/api/auth/users/${userId}`, {
            method: 'DELETE',
            headers: { 'X-CSRFToken': getCSRFToken() }
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            errorBox.textContent = data.error || t('failedDelete', 'Failed to delete user.');
            errorBox.classList.remove('d-none');
            return;
        }
        bootstrap.Modal.getInstance(document.getElementById('deleteUserModal'))?.hide();
        loadUsers();
    } finally {
        confirmBtn.disabled = false;
    }
}

function showCreateUserModal() {
    const modal = new bootstrap.Modal(document.getElementById('createUserModal'));
    document.getElementById('createUserError').classList.add('d-none');
    document.getElementById('createUserForm').reset();
    modal.show();
    setTimeout(() => document.getElementById('newUsername').focus(), 300);
}

function setupCreateUserForm() {
    const form = document.getElementById('createUserForm');
    if (!form) return;
    form.addEventListener('submit', async function (event) {
        event.preventDefault();
        const errorBox = document.getElementById('createUserError');
        errorBox.classList.add('d-none');

        const username = document.getElementById('newUsername').value.trim();
        const password = document.getElementById('newUserPassword').value;
        const role = document.getElementById('newUserRole').value;
        const mustChange = document.getElementById('newUserMustChange').checked;

        if (!username || !password) {
            errorBox.textContent = t('usernamePasswordRequired', 'Username and password are required.');
            errorBox.classList.remove('d-none');
            return;
        }
        if (password.length < 12) {
            errorBox.textContent = t('passwordTooShort', 'Password must be at least 12 characters.');
            errorBox.classList.remove('d-none');
            return;
        }

        const submitBtn = document.getElementById('createUserSubmit');
        window.InforaxisDataInterface?.setButtonBusy(submitBtn, true, { label: t('creating', 'Creating') });
        if (!window.InforaxisDataInterface) submitBtn.disabled = true;
        try {
            const response = await fetch('/api/auth/users', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken() },
                body: JSON.stringify({ username, password, role, must_change_password: mustChange })
            });
            const data = await response.json().catch(() => ({}));
            if (response.ok && data.success) {
                bootstrap.Modal.getInstance(document.getElementById('createUserModal')).hide();
                notify(t('userCreated', 'User created successfully'), 'success');
                loadUsers();
            } else {
                errorBox.textContent = data.error || t('failedCreate', 'Failed to create user.');
                errorBox.classList.remove('d-none');
            }
        } catch (error) {
            errorBox.textContent = `${t('error', 'Error')}: ${error.message}`;
            errorBox.classList.remove('d-none');
        } finally {
            window.InforaxisDataInterface?.setButtonBusy(submitBtn, false);
            if (!window.InforaxisDataInterface) submitBtn.disabled = false;
        }
    });
}

function setupUserWorkbenchControls() {
    document.getElementById('createUserTrigger')?.addEventListener('click', showCreateUserModal);
    document.getElementById('refreshUsers')?.addEventListener('click', loadUsers);
    ['userSearchFilter', 'userRoleFilter', 'userStatusFilter'].forEach((id) => {
        const element = document.getElementById(id);
        if (!element) return;
        element.addEventListener(id === 'userSearchFilter' ? 'input' : 'change', applyUserFilters);
    });

    document.getElementById('usersTableBody')?.addEventListener('change', (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement)) return;
        if (target.matches('.user-role-select, .user-active-toggle')) {
            updateUser(parseInt(target.dataset.userId, 10));
        }
    });

    document.getElementById('usersTableBody')?.addEventListener('click', (event) => {
        if (!(event.target instanceof Element)) return;
        const buttonEl = event.target.closest('[data-user-action]');
        if (!buttonEl) return;
        const userId = parseInt(buttonEl.dataset.userId, 10);
        const user = allUsers.find((item) => item.id === userId);
        if (buttonEl.dataset.userAction === 'reset') resetPassword(userId);
        if (buttonEl.dataset.userAction === 'delete') showDeleteUserModal(userId, user?.username || '');
    });

    const confirmBtn = document.getElementById('deleteUserConfirm');
    confirmBtn?.addEventListener('click', function () {
        deleteUser(parseInt(confirmBtn.dataset.userId, 10));
    });
}

function initUsersPage() {
    const pageDataEl = document.getElementById('users-page-data');
    if (pageDataEl) {
        try {
            const data = JSON.parse(pageDataEl.textContent);
            translations = data.translations || {};
            currentUserId = data.currentUserId || null;
            window.translations = window.translations || {};
            Object.assign(window.translations, translations);
        } catch (error) {
            console.error('Error parsing users page data:', error);
        }
    }
    setupUserWorkbenchControls();
    setupCreateUserForm();
    loadUsers();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initUsersPage);
} else {
    initUsersPage();
}

window.showCreateUserModal = showCreateUserModal;
window.updateUser = updateUser;
window.resetPassword = resetPassword;
window.showDeleteUserModal = showDeleteUserModal;
window.deleteUser = deleteUser;
window.loadUsers = loadUsers;

export default function init() {
    return Promise.resolve();
}
