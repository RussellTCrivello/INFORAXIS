/**
 * User Management page (/users, admin-only).
 * Wired to GET/POST /api/auth/users, PATCH /api/auth/users/<id>,
 * POST /api/auth/users/<id>/reset-password.
 */

let translations = {};
let currentUserId = null;

function getCSRFToken() {
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    return metaTag ? metaTag.getAttribute('content') : '';
}

function escapeHtml(value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

async function loadUsers() {
    const tbody = document.getElementById('usersTableBody');
    if (!tbody) return;
    try {
        const response = await fetch('/api/auth/users', {
            headers: { 'X-CSRFToken': getCSRFToken() }
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        const users = Array.isArray(data.users) ? data.users : [];

        const countEl = document.getElementById('usersCount');
        if (countEl) countEl.textContent = users.length;

        if (users.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center py-4 text-muted">No users found.</td></tr>`;
            return;
        }

        tbody.innerHTML = users.map(u => renderUserRow(u)).join('');
    } catch (error) {
        tbody.innerHTML = `<tr><td colspan="6" class="text-center py-4 text-danger">
            ${escapeHtml(translations.error || 'Error')}: ${escapeHtml(error.message)}
        </td></tr>`;
    }
}

function renderUserRow(u) {
    const isSelf = u.id === currentUserId;
    const roleBadge = {
        admin: 'bg-danger',
        analyst: 'bg-primary',
        viewer: 'bg-secondary'
    }[u.role] || 'bg-secondary';
    const created = u.created_at ? String(u.created_at).slice(0, 10) : '—';
    return `
        <tr data-user-id="${u.id}">
            <td>${u.id}</td>
            <td>
                <strong>${escapeHtml(u.username)}</strong>
                ${isSelf ? `<span class="badge bg-info ms-1">You</span>` : ''}
                ${u.must_change_password ? `<span class="badge bg-warning text-dark ms-1" title="Must change password at next sign-in">temp pw</span>` : ''}
            </td>
            <td>
                ${isSelf
                    ? `<span class="badge ${roleBadge}">${escapeHtml(u.role)}</span>`
                    : `<select class="form-select form-select-sm user-role-select" style="max-width: 130px;" onchange="updateUser(${u.id})" aria-label="Role for ${escapeHtml(u.username)}">
                        ${['viewer', 'analyst', 'admin'].map(r =>
                            `<option value="${r}" ${r === u.role ? 'selected' : ''}>${r.charAt(0).toUpperCase() + r.slice(1)}</option>`
                        ).join('')}
                    </select>`}
            </td>
            <td>
                <div class="form-check form-switch">
                    <input class="form-check-input user-active-toggle" type="checkbox" role="switch"
                           ${u.is_active ? 'checked' : ''} ${isSelf ? 'disabled' : ''}
                           onchange="updateUser(${u.id})" aria-label="Active status for ${escapeHtml(u.username)}">
                </div>
            </td>
            <td>${created}</td>
            <td class="text-end">
                <button class="btn btn-sm btn-outline-warning" onclick="resetPassword(${u.id})"
                        title="Generate a new temporary password">
                    <i class="bi bi-key"></i> Reset PW
                </button>
                ${isSelf ? '' : `
                <button class="btn btn-sm btn-outline-danger" onclick="showDeleteUserModal(${u.id}, '${escapeHtml(u.username)}')"
                        title="Permanently delete this account">
                    <i class="bi bi-trash"></i>
                </button>`}
            </td>
        </tr>`;
}

async function updateUser(userId) {
    const row = document.querySelector(`tr[data-user-id="${userId}"]`);
    if (!row) return;
    const role = row.querySelector('.user-role-select')?.value;
    const isActive = row.querySelector('.user-active-toggle')?.checked;

    // Guard: an admin cannot lock themselves out of the admin role.
    if (userId === currentUserId) {
        alert(translations.cannotChangeSelf || 'You cannot change your own role or status.');
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
        alert((translations.error || 'Error') + ': ' + (err.error || translations.unknownError || 'Unknown error'));
    }
    loadUsers();
}

async function resetPassword(userId) {
    if (!confirm(translations.confirmReset || 'Generate a new temporary password for this user?')) return;
    const response = await fetch(`/api/auth/users/${userId}/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken() }
    });
    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        alert((translations.error || 'Error') + ': ' + (err.error || translations.unknownError || 'Unknown error'));
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
            errorBox.textContent = data.error || 'Failed to delete user.';
            errorBox.classList.remove('d-none');
            return;
        }
        bootstrap.Modal.getInstance(document.getElementById('deleteUserModal'))?.hide();
        loadUsers();
    } finally {
        confirmBtn.disabled = false;
    }
}

document.addEventListener('DOMContentLoaded', function () {
    const confirmBtn = document.getElementById('deleteUserConfirm');
    if (confirmBtn) {
        confirmBtn.addEventListener('click', function () {
            deleteUser(parseInt(confirmBtn.dataset.userId, 10));
        });
    }
});

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
    form.addEventListener('submit', async function (e) {
        e.preventDefault();
        const errorBox = document.getElementById('createUserError');
        errorBox.classList.add('d-none');

        const username = document.getElementById('newUsername').value.trim();
        const password = document.getElementById('newUserPassword').value;
        const role = document.getElementById('newUserRole').value;
        const mustChange = document.getElementById('newUserMustChange').checked;

        if (!username || !password) {
            errorBox.textContent = 'Username and password are required.';
            errorBox.classList.remove('d-none');
            return;
        }
        if (password.length < 12) {
            errorBox.textContent = 'Password must be at least 12 characters.';
            errorBox.classList.remove('d-none');
            return;
        }

        const submitBtn = document.getElementById('createUserSubmit');
        submitBtn.disabled = true;
        try {
            const response = await fetch('/api/auth/users', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken() },
                body: JSON.stringify({ username, password, role, must_change_password: mustChange })
            });
            const data = await response.json().catch(() => ({}));
            if (response.ok && data.success) {
                bootstrap.Modal.getInstance(document.getElementById('createUserModal')).hide();
                loadUsers();
            } else {
                errorBox.textContent = data.error || 'Failed to create user.';
                errorBox.classList.remove('d-none');
            }
        } catch (error) {
            errorBox.textContent = 'Error: ' + error.message;
            errorBox.classList.remove('d-none');
        } finally {
            submitBtn.disabled = false;
        }
    });
}

document.addEventListener('DOMContentLoaded', function () {
    const pageDataEl = document.getElementById('users-page-data');
    if (pageDataEl) {
        try {
            const data = JSON.parse(pageDataEl.textContent);
            translations = data.translations || {};
            currentUserId = data.currentUserId || null;
            window.translations = window.translations || {};
            Object.assign(window.translations, translations);
        } catch (e) {
            console.error('Error parsing users page data:', e);
        }
    }
    setupCreateUserForm();
    loadUsers();
});

window.showCreateUserModal = showCreateUserModal;
window.updateUser = updateUser;
window.resetPassword = resetPassword;
window.showDeleteUserModal = showDeleteUserModal;
window.deleteUser = deleteUser;
window.loadUsers = loadUsers;

export default function init() {
    return Promise.resolve();
}
