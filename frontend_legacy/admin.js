/**
 * Admin Console JavaScript
 * Handles all admin functionality: users, jobs, rate limits, audit logs
 */

// ==================== Configuration ====================
const ADMIN_API_BASE = '/api/v1/admin';
const REFRESH_INTERVAL = 30000; // 30 seconds

// ==================== State ====================
const AdminState = {
    currentTab: 'dashboard',
    users: { page: 1, perPage: 20, filters: {} },
    jobs: { page: 1, perPage: 20, filters: {} },
    audit: { page: 1, perPage: 50, filters: {} },
    refreshTimers: {},
};

// ==================== Initialization ====================
document.addEventListener('DOMContentLoaded', async () => {
    // Check authentication
    if (!AuthManager.isAuthenticated()) {
        window.location.href = 'index.html';
        return;
    }

    // Check if user is admin
    const user = AuthManager.getUser();
    if (!user || !user.is_superuser) {
        showToast('Keine Administratorrechte', 'error');
        setTimeout(() => {
            window.location.href = 'index.html';
        }, 2000);
        return;
    }

    // Initialize display mode
    initDisplayMode();

    // Set up event listeners
    setupEventListeners();

    // Load initial data
    await loadDashboard();

    // Start auto-refresh
    startAutoRefresh();
});

// ==================== Event Listeners ====================
function setupEventListeners() {
    // Navigation tabs
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    // Display mode switcher
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.addEventListener('click', () => setDisplayMode(btn.dataset.mode));
    });

    // Logout
    document.getElementById('admin-logout-btn')?.addEventListener('click', () => {
        AuthManager.logout();
        window.location.href = 'index.html';
    });

    // Dashboard actions
    document.getElementById('clear-gpu-cache-btn')?.addEventListener('click', clearGPUCache);
    document.getElementById('refresh-queue-btn')?.addEventListener('click', loadDashboard);

    // User management
    document.getElementById('create-user-btn')?.addEventListener('click', () => showUserModal());
    document.getElementById('user-search')?.addEventListener('input', debounce(loadUsers, 300));
    document.getElementById('user-role-filter')?.addEventListener('change', loadUsers);
    document.getElementById('user-status-filter')?.addEventListener('change', loadUsers);
    document.getElementById('user-tier-filter')?.addEventListener('change', loadUsers);
    document.getElementById('user-submit-btn')?.addEventListener('click', submitUser);

    // Job management
    document.getElementById('clear-queue-btn')?.addEventListener('click', confirmClearQueue);
    document.getElementById('job-status-filter')?.addEventListener('change', loadJobs);
    document.getElementById('job-backend-filter')?.addEventListener('change', loadJobs);
    document.getElementById('job-error-filter')?.addEventListener('change', loadJobs);

    // Rate limit management
    document.getElementById('rate-limit-submit-btn')?.addEventListener('click', submitRateLimitOverride);
    document.getElementById('delete-override-btn')?.addEventListener('click', deleteRateLimitOverride);

    // Audit log
    document.getElementById('export-audit-btn')?.addEventListener('click', exportAuditLogs);
    document.getElementById('audit-action-filter')?.addEventListener('input', debounce(loadAuditLogs, 300));
    document.getElementById('audit-resource-filter')?.addEventListener('change', loadAuditLogs);
    document.getElementById('audit-from-date')?.addEventListener('change', loadAuditLogs);
    document.getElementById('audit-to-date')?.addEventListener('change', loadAuditLogs);
    document.getElementById('audit-success-filter')?.addEventListener('change', loadAuditLogs);
}

// ==================== Tab Navigation ====================
function switchTab(tabName) {
    AdminState.currentTab = tabName;

    // Update nav buttons
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabName);
    });

    // Update tabs
    document.querySelectorAll('.admin-tab').forEach(tab => {
        tab.classList.toggle('active', tab.id === `${tabName}-tab`);
    });

    // Load tab data
    switch (tabName) {
        case 'dashboard':
            loadDashboard();
            break;
        case 'users':
            loadUsers();
            break;
        case 'jobs':
            loadJobs();
            break;
        case 'rate-limits':
            loadRateLimits();
            break;
        case 'audit':
            loadAuditLogs();
            break;
    }
}

// ==================== Dashboard ====================
async function loadDashboard() {
    try {
        const dashboard = await apiCall(`${ADMIN_API_BASE}/system/dashboard`);
        updateDashboard(dashboard);
    } catch (error) {
        console.error('Error loading dashboard:', error);
        showToast('Fehler beim Laden des Dashboards', 'error');
    }
}

function updateDashboard(data) {
    // GPU Status
    if (data.gpu) {
        const vramPercent = (data.gpu.memory_used_gb / data.gpu.memory_total_gb) * 100;
        document.getElementById('vram-progress').style.width = `${vramPercent}%`;
        document.getElementById('vram-detail').textContent =
            `${data.gpu.memory_used_gb.toFixed(1)} / ${data.gpu.memory_total_gb.toFixed(1)} GB`;
        document.getElementById('gpu-utilization').textContent = `${data.gpu.utilization_percent || 0}%`;
        document.getElementById('gpu-temp').textContent = `${data.gpu.temperature || '--'} C`;

        // Update header GPU status
        document.getElementById('gpu-name').textContent = data.gpu.device_name || 'Nicht verfuegbar';
        document.getElementById('vram-usage').textContent = data.gpu.memory_used_gb.toFixed(1);
        document.getElementById('gpu-indicator').className =
            `gpu-indicator ${data.gpu.available ? 'available' : 'unavailable'}`;
    }

    // Queue Status
    if (data.queue) {
        document.getElementById('pending-jobs').textContent = data.queue.pending || 0;
        document.getElementById('processing-jobs').textContent = data.queue.processing || 0;
        document.getElementById('failed-jobs').textContent = data.queue.failed || 0;
        document.getElementById('avg-wait-time').textContent =
            data.queue.avg_wait_time_ms ? `${data.queue.avg_wait_time_ms.toFixed(0)} ms` : '-- ms';
    }

    // Health Status
    if (data.health) {
        updateHealthItem('postgresql', data.health.postgresql);
        updateHealthItem('redis', data.health.redis);
        updateHealthItem('minio', data.health.minio);
        updateHealthItem('celery', data.health.celery);
    }

    // Processing Stats
    if (data.stats) {
        document.getElementById('docs-processed').textContent = data.stats.total_processed || 0;
        document.getElementById('success-rate').textContent =
            data.stats.success_rate ? `${(data.stats.success_rate * 100).toFixed(1)}%` : '0%';
        document.getElementById('avg-processing-time').textContent =
            data.stats.avg_processing_time_ms ? `${data.stats.avg_processing_time_ms.toFixed(0)} ms` : '-- ms';
    }

    // Backend Status
    updateBackendGrid(data.backends || {});
}

function updateHealthItem(service, status) {
    const item = document.getElementById(`health-${service}`);
    if (item) {
        item.className = `health-item ${status?.healthy ? 'healthy' : 'unhealthy'}`;
    }
}

function updateBackendGrid(backends) {
    const grid = document.getElementById('backend-grid');
    if (!grid) return;

    const backendInfo = {
        deepseek_janus: { name: 'DeepSeek-Janus-Pro', vram: '12 GB' },
        got_ocr: { name: 'GOT-OCR 2.0', vram: '10 GB' },
        surya: { name: 'Surya + Docling', vram: '0 GB (CPU)' },
        surya_gpu: { name: 'Surya GPU', vram: '4 GB' },
    };

    grid.innerHTML = Object.entries(backendInfo).map(([key, info]) => {
        const status = backends[key]?.status || 'unknown';
        return `
            <div class="backend-card ${status === 'available' ? 'available' : 'unavailable'}">
                <div class="backend-name">${info.name}</div>
                <span class="backend-status ${status}">${status === 'available' ? 'Verfuegbar' : 'Nicht verfuegbar'}</span>
                <div class="backend-vram">VRAM: ${info.vram}</div>
            </div>
        `;
    }).join('');
}

async function clearGPUCache() {
    try {
        await apiCall(`${ADMIN_API_BASE}/system/gpu/clear-cache`, { method: 'POST' });
        showToast('GPU-Cache wurde geleert', 'success');
        loadDashboard();
    } catch (error) {
        showToast('Fehler beim Leeren des GPU-Cache', 'error');
    }
}

// ==================== User Management ====================
async function loadUsers() {
    const search = document.getElementById('user-search')?.value || '';
    const role = document.getElementById('user-role-filter')?.value || '';
    const status = document.getElementById('user-status-filter')?.value || '';
    const tier = document.getElementById('user-tier-filter')?.value || '';

    const params = new URLSearchParams({
        page: AdminState.users.page,
        per_page: AdminState.users.perPage,
    });

    if (search) params.append('search', search);
    if (role) params.append('role', role);
    if (status) params.append('status', status);
    if (tier) params.append('tier', tier);

    try {
        const data = await apiCall(`${ADMIN_API_BASE}/users?${params}`);
        renderUsersTable(data.users);
        renderPagination('users', data);
    } catch (error) {
        console.error('Error loading users:', error);
        showToast('Fehler beim Laden der Benutzer', 'error');
    }
}

function renderUsersTable(users) {
    const tbody = document.getElementById('users-tbody');
    if (!tbody) return;

    if (!users || users.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center">Keine Benutzer gefunden</td></tr>';
        return;
    }

    tbody.innerHTML = users.map(user => `
        <tr>
            <td>${escapeHtml(user.email)}</td>
            <td>${escapeHtml(user.username)}</td>
            <td><span class="role-badge ${user.role}">${user.role}</span></td>
            <td><span class="tier-badge ${user.tier}">${user.tier}</span></td>
            <td><span class="status-badge ${user.status}">${user.status}</span></td>
            <td>${user.last_login ? formatDate(user.last_login) : 'Nie'}</td>
            <td>${user.documents_processed_today || 0}</td>
            <td class="action-buttons">
                <button class="btn-icon" onclick="showUserModal('${user.id}')" title="Bearbeiten">✏️</button>
                <button class="btn-icon" onclick="showRateLimitModal('${user.id}', '${user.email}')" title="Rate Limits">⏱️</button>
                ${user.status !== 'deactivated'
                    ? `<button class="btn-icon" onclick="confirmDeactivateUser('${user.id}')" title="Deaktivieren">🚫</button>`
                    : `<button class="btn-icon" onclick="activateUser('${user.id}')" title="Aktivieren">✅</button>`
                }
                <button class="btn-icon" onclick="confirmResetPassword('${user.id}')" title="Passwort zuruecksetzen">🔑</button>
            </td>
        </tr>
    `).join('');
}

async function showUserModal(userId = null) {
    const modal = document.getElementById('user-modal');
    const title = document.getElementById('user-modal-title');
    const form = document.getElementById('user-form');
    const passwordGroup = document.getElementById('password-group');

    form.reset();

    if (userId) {
        title.textContent = 'Benutzer bearbeiten';
        passwordGroup.style.display = 'none';

        try {
            const user = await apiCall(`${ADMIN_API_BASE}/users/${userId}`);
            document.getElementById('user-email').value = user.email || '';
            document.getElementById('user-username').value = user.username || '';
            document.getElementById('user-fullname').value = user.full_name || '';
            document.getElementById('user-tier').value = user.tier || 'free';
            document.getElementById('user-quota').value = user.daily_quota || 50;
            document.getElementById('user-superuser').checked = user.is_superuser || false;
            document.getElementById('user-notes').value = user.notes || '';
            form.dataset.userId = userId;
        } catch (error) {
            showToast('Fehler beim Laden des Benutzers', 'error');
            return;
        }
    } else {
        title.textContent = 'Neuer Benutzer';
        passwordGroup.style.display = 'block';
        delete form.dataset.userId;
    }

    modal.style.display = 'flex';
}

async function submitUser() {
    const form = document.getElementById('user-form');
    const userId = form.dataset.userId;

    const data = {
        email: document.getElementById('user-email').value,
        username: document.getElementById('user-username').value,
        full_name: document.getElementById('user-fullname').value || null,
        tier: document.getElementById('user-tier').value,
        daily_quota: parseInt(document.getElementById('user-quota').value),
        is_superuser: document.getElementById('user-superuser').checked,
        notes: document.getElementById('user-notes').value || null,
    };

    if (!userId) {
        data.password = document.getElementById('user-password').value;
        if (!data.password || data.password.length < 8) {
            showToast('Passwort muss mindestens 8 Zeichen lang sein', 'error');
            return;
        }
    }

    try {
        if (userId) {
            await apiCall(`${ADMIN_API_BASE}/users/${userId}`, {
                method: 'PATCH',
                body: JSON.stringify(data),
            });
            showToast('Benutzer wurde aktualisiert', 'success');
        } else {
            await apiCall(`${ADMIN_API_BASE}/users`, {
                method: 'POST',
                body: JSON.stringify(data),
            });
            showToast('Benutzer wurde erstellt', 'success');
        }

        AdminUI.closeModal('user-modal');
        loadUsers();
    } catch (error) {
        showToast(`Fehler: ${error.message}`, 'error');
    }
}

async function confirmDeactivateUser(userId) {
    if (await showConfirmDialog('Benutzer deaktivieren', 'Moechten Sie diesen Benutzer wirklich deaktivieren?')) {
        try {
            await apiCall(`${ADMIN_API_BASE}/users/${userId}/deactivate`, { method: 'POST' });
            showToast('Benutzer wurde deaktiviert', 'success');
            loadUsers();
        } catch (error) {
            showToast('Fehler beim Deaktivieren', 'error');
        }
    }
}

async function activateUser(userId) {
    try {
        await apiCall(`${ADMIN_API_BASE}/users/${userId}/activate`, { method: 'POST' });
        showToast('Benutzer wurde aktiviert', 'success');
        loadUsers();
    } catch (error) {
        showToast('Fehler beim Aktivieren', 'error');
    }
}

async function confirmResetPassword(userId) {
    if (await showConfirmDialog('Passwort zuruecksetzen', 'Moechten Sie das Passwort wirklich zuruecksetzen?')) {
        try {
            const result = await apiCall(`${ADMIN_API_BASE}/users/${userId}/reset-password`, { method: 'POST' });
            showToast(`Temporaeres Passwort: ${result.temporary_password}`, 'success', 10000);
        } catch (error) {
            showToast('Fehler beim Zuruecksetzen des Passworts', 'error');
        }
    }
}

// ==================== Job Management ====================
async function loadJobs() {
    const status = document.getElementById('job-status-filter')?.value || '';
    const backend = document.getElementById('job-backend-filter')?.value || '';
    const hasError = document.getElementById('job-error-filter')?.checked;

    const params = new URLSearchParams({
        page: AdminState.jobs.page,
        per_page: AdminState.jobs.perPage,
    });

    if (status) params.append('status', status);
    if (backend) params.append('backend', backend);
    if (hasError) params.append('has_error', 'true');

    try {
        const data = await apiCall(`${ADMIN_API_BASE}/jobs?${params}`);
        renderJobsTable(data.jobs);
        renderJobStatusSummary(data.status_summary);
        renderPagination('jobs', data);
    } catch (error) {
        console.error('Error loading jobs:', error);
        showToast('Fehler beim Laden der Auftraege', 'error');
    }
}

function renderJobsTable(jobs) {
    const tbody = document.getElementById('jobs-tbody');
    if (!tbody) return;

    if (!jobs || jobs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center">Keine Auftraege gefunden</td></tr>';
        return;
    }

    tbody.innerHTML = jobs.map(job => `
        <tr>
            <td>${escapeHtml(job.document_filename || 'Unbekannt')}</td>
            <td>${escapeHtml(job.backend || 'auto')}</td>
            <td><span class="status-badge ${job.status}">${job.status}</span></td>
            <td>${job.priority || '-'}</td>
            <td>${formatDate(job.created_at)}</td>
            <td>${job.duration_ms ? `${job.duration_ms} ms` : '-'}</td>
            <td>${escapeHtml(job.user_email || '-')}</td>
            <td class="action-buttons">
                ${job.status === 'pending' || job.status === 'processing'
                    ? `<button class="btn-icon" onclick="cancelJob('${job.id}')" title="Abbrechen">❌</button>`
                    : ''
                }
                ${job.status === 'failed'
                    ? `<button class="btn-icon" onclick="retryJob('${job.id}')" title="Wiederholen">🔄</button>`
                    : ''
                }
            </td>
        </tr>
    `).join('');
}

function renderJobStatusSummary(summary) {
    const container = document.getElementById('job-status-summary');
    if (!container || !summary) return;

    container.innerHTML = Object.entries(summary).map(([status, count]) => `
        <div class="status-summary-item">
            <span class="status-badge ${status}">${status}</span>
            <span>${count}</span>
        </div>
    `).join('');
}

async function cancelJob(jobId) {
    try {
        await apiCall(`${ADMIN_API_BASE}/jobs/${jobId}/cancel`, { method: 'POST' });
        showToast('Auftrag wurde abgebrochen', 'success');
        loadJobs();
    } catch (error) {
        showToast('Fehler beim Abbrechen', 'error');
    }
}

async function retryJob(jobId) {
    try {
        await apiCall(`${ADMIN_API_BASE}/jobs/${jobId}/retry`, { method: 'POST' });
        showToast('Auftrag wird wiederholt', 'success');
        loadJobs();
    } catch (error) {
        showToast('Fehler beim Wiederholen', 'error');
    }
}

async function confirmClearQueue() {
    if (await showConfirmDialog('Warteschlange leeren', 'Moechten Sie wirklich alle wartenden Auftraege loeschen?')) {
        try {
            const result = await apiCall(`${ADMIN_API_BASE}/jobs/queue/clear`, { method: 'POST' });
            showToast(`${result.cleared_count} Auftraege geloescht`, 'success');
            loadJobs();
            loadDashboard();
        } catch (error) {
            showToast('Fehler beim Leeren der Warteschlange', 'error');
        }
    }
}

// ==================== Rate Limits ====================
async function loadRateLimits() {
    try {
        // Load tier defaults
        const tiers = await apiCall(`${ADMIN_API_BASE}/rate-limits/tiers`);
        renderTierDefaults(tiers.tiers);

        // Load usage stats
        const stats = await apiCall(`${ADMIN_API_BASE}/rate-limits/stats`);
        renderUsageStats(stats);
    } catch (error) {
        console.error('Error loading rate limits:', error);
        showToast('Fehler beim Laden der Rate Limits', 'error');
    }
}

function renderTierDefaults(tiers) {
    const grid = document.getElementById('tier-defaults-grid');
    if (!grid) return;

    grid.innerHTML = Object.entries(tiers).map(([tier, defaults]) => `
        <div class="tier-card">
            <h4><span class="tier-badge ${tier}">${tier.toUpperCase()}</span></h4>
            <div class="tier-limits">
                <div class="limit-row">
                    <span>OCR/Stunde:</span>
                    <span>${defaults.ocr_hourly}</span>
                </div>
                <div class="limit-row">
                    <span>OCR/Tag:</span>
                    <span>${defaults.ocr_daily}</span>
                </div>
                <div class="limit-row">
                    <span>Batch/Stunde:</span>
                    <span>${defaults.batch_hourly}</span>
                </div>
                <div class="limit-row">
                    <span>API/Minute:</span>
                    <span>${defaults.api_per_minute}</span>
                </div>
            </div>
        </div>
    `).join('');
}

function renderUsageStats(stats) {
    document.getElementById('total-users').textContent = stats.total_users || 0;
    document.getElementById('users-at-limit').textContent = stats.users_at_limit || 0;
    document.getElementById('users-with-overrides').textContent = stats.users_with_overrides || 0;

    // Top users
    const list = document.getElementById('top-users-list');
    if (list && stats.top_users_by_usage) {
        list.innerHTML = stats.top_users_by_usage.map((user, index) => `
            <div class="top-user-item">
                <span class="top-user-rank">#${index + 1}</span>
                <span class="top-user-email">${escapeHtml(user.email)}</span>
                <span class="top-user-count">${user.documents_today} Dok.</span>
            </div>
        `).join('') || '<div class="top-user-item">Keine Daten</div>';
    }
}

async function showRateLimitModal(userId, email) {
    const modal = document.getElementById('rate-limit-modal');
    document.getElementById('rate-limit-user-id').value = userId;
    document.getElementById('rate-limit-user-email').textContent = email;

    // Reset form
    document.getElementById('ocr-hourly').value = '';
    document.getElementById('ocr-daily').value = '';
    document.getElementById('batch-hourly').value = '';
    document.getElementById('api-per-minute').value = '';
    document.getElementById('override-valid-until').value = '';
    document.getElementById('override-reason').value = '';

    try {
        const status = await apiCall(`${ADMIN_API_BASE}/rate-limits/users/${userId}`);
        if (status.has_override) {
            document.getElementById('delete-override-btn').style.display = 'block';
            // Populate form with existing override values if available
        } else {
            document.getElementById('delete-override-btn').style.display = 'none';
        }
    } catch (error) {
        document.getElementById('delete-override-btn').style.display = 'none';
    }

    modal.style.display = 'flex';
}

async function submitRateLimitOverride() {
    const userId = document.getElementById('rate-limit-user-id').value;

    const data = {
        ocr_hourly: parseInt(document.getElementById('ocr-hourly').value) || null,
        ocr_daily: parseInt(document.getElementById('ocr-daily').value) || null,
        batch_hourly: parseInt(document.getElementById('batch-hourly').value) || null,
        api_per_minute: parseInt(document.getElementById('api-per-minute').value) || null,
        valid_until: document.getElementById('override-valid-until').value || null,
        reason: document.getElementById('override-reason').value || null,
    };

    try {
        await apiCall(`${ADMIN_API_BASE}/rate-limits/users/${userId}/override`, {
            method: 'POST',
            body: JSON.stringify(data),
        });
        showToast('Rate Limit Override wurde gespeichert', 'success');
        AdminUI.closeModal('rate-limit-modal');
        loadRateLimits();
    } catch (error) {
        showToast('Fehler beim Speichern', 'error');
    }
}

async function deleteRateLimitOverride() {
    const userId = document.getElementById('rate-limit-user-id').value;

    try {
        await apiCall(`${ADMIN_API_BASE}/rate-limits/users/${userId}/override`, {
            method: 'DELETE',
        });
        showToast('Override wurde geloescht', 'success');
        AdminUI.closeModal('rate-limit-modal');
        loadRateLimits();
    } catch (error) {
        showToast('Fehler beim Loeschen', 'error');
    }
}

// ==================== Audit Logs ====================
async function loadAuditLogs() {
    const action = document.getElementById('audit-action-filter')?.value || '';
    const resourceType = document.getElementById('audit-resource-filter')?.value || '';
    const fromDate = document.getElementById('audit-from-date')?.value || '';
    const toDate = document.getElementById('audit-to-date')?.value || '';
    const success = document.getElementById('audit-success-filter')?.checked;

    const params = new URLSearchParams({
        page: AdminState.audit.page,
        per_page: AdminState.audit.perPage,
    });

    if (action) params.append('action', action);
    if (resourceType) params.append('resource_type', resourceType);
    if (fromDate) params.append('from_date', fromDate);
    if (toDate) params.append('to_date', toDate);
    if (success) params.append('success', 'true');

    try {
        const data = await apiCall(`${ADMIN_API_BASE}/audit/logs?${params}`);
        renderAuditTable(data.logs);
        renderPagination('audit', data);
    } catch (error) {
        console.error('Error loading audit logs:', error);
        showToast('Fehler beim Laden der Audit-Logs', 'error');
    }
}

function renderAuditTable(logs) {
    const tbody = document.getElementById('audit-tbody');
    if (!tbody) return;

    if (!logs || logs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center">Keine Eintraege gefunden</td></tr>';
        return;
    }

    tbody.innerHTML = logs.map(log => `
        <tr>
            <td>${formatDate(log.created_at)}</td>
            <td>${escapeHtml(log.user_email || '-')}</td>
            <td>${escapeHtml(log.action)}</td>
            <td>${escapeHtml(log.resource_type || '-')} ${log.resource_id ? `(${log.resource_id.slice(0, 8)}...)` : ''}</td>
            <td>${escapeHtml(log.ip_address || '-')}</td>
            <td><span class="status-badge ${log.success ? 'completed' : 'failed'}">${log.success ? 'OK' : 'Fehler'}</span></td>
        </tr>
    `).join('');
}

async function exportAuditLogs() {
    const params = new URLSearchParams({ format: 'csv' });

    try {
        const response = await fetch(`${ADMIN_API_BASE}/audit/export?${params}`, {
            headers: {
                'Authorization': `Bearer ${AuthManager.getAccessToken()}`,
            },
        });

        if (!response.ok) throw new Error('Export failed');

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `audit_logs_${new Date().toISOString().split('T')[0]}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);

        showToast('Export erfolgreich', 'success');
    } catch (error) {
        showToast('Fehler beim Export', 'error');
    }
}

// ==================== Pagination ====================
function renderPagination(type, data) {
    const container = document.getElementById(`${type}-pagination`);
    if (!container) return;

    const { page, total_pages } = data;

    let html = '';

    if (total_pages > 1) {
        html += `<button class="page-btn" onclick="goToPage('${type}', 1)" ${page === 1 ? 'disabled' : ''}>«</button>`;
        html += `<button class="page-btn" onclick="goToPage('${type}', ${page - 1})" ${page === 1 ? 'disabled' : ''}>‹</button>`;

        const startPage = Math.max(1, page - 2);
        const endPage = Math.min(total_pages, page + 2);

        for (let i = startPage; i <= endPage; i++) {
            html += `<button class="page-btn ${i === page ? 'active' : ''}" onclick="goToPage('${type}', ${i})">${i}</button>`;
        }

        html += `<button class="page-btn" onclick="goToPage('${type}', ${page + 1})" ${page === total_pages ? 'disabled' : ''}>›</button>`;
        html += `<button class="page-btn" onclick="goToPage('${type}', ${total_pages})" ${page === total_pages ? 'disabled' : ''}>»</button>`;

        html += `<span class="page-info">Seite ${page} von ${total_pages}</span>`;
    }

    container.innerHTML = html;
}

function goToPage(type, page) {
    AdminState[type].page = page;

    switch (type) {
        case 'users':
            loadUsers();
            break;
        case 'jobs':
            loadJobs();
            break;
        case 'audit':
            loadAuditLogs();
            break;
    }
}

// ==================== UI Helpers ====================
const AdminUI = {
    closeModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.style.display = 'none';
        }
    }
};

async function showConfirmDialog(title, message) {
    return new Promise((resolve) => {
        const modal = document.getElementById('confirm-modal');
        document.getElementById('confirm-title').textContent = title;
        document.getElementById('confirm-message').textContent = message;

        const okBtn = document.getElementById('confirm-ok-btn');
        const cancelBtn = document.getElementById('confirm-cancel-btn');

        const handleOk = () => {
            cleanup();
            modal.style.display = 'none';
            resolve(true);
        };

        const handleCancel = () => {
            cleanup();
            modal.style.display = 'none';
            resolve(false);
        };

        const cleanup = () => {
            okBtn.removeEventListener('click', handleOk);
            cancelBtn.removeEventListener('click', handleCancel);
        };

        okBtn.addEventListener('click', handleOk);
        cancelBtn.addEventListener('click', handleCancel);

        modal.style.display = 'flex';
    });
}

function showToast(message, type = 'info', duration = 5000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    container.appendChild(toast);

    setTimeout(() => toast.classList.add('show'), 10);

    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// ==================== API Helper ====================
async function apiCall(url, options = {}) {
    const token = AuthManager.getAccessToken();

    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
        },
    };

    const response = await fetch(url, { ...defaultOptions, ...options });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unbekannter Fehler' }));
        throw new Error(error.detail || 'Request failed');
    }

    return response.json();
}

// ==================== Utility Functions ====================
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleDateString('de-DE', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    });
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function initDisplayMode() {
    const savedMode = localStorage.getItem('displayMode') || 'dark';
    setDisplayMode(savedMode);
}

function setDisplayMode(mode) {
    document.body.dataset.mode = mode;
    localStorage.setItem('displayMode', mode);

    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === mode);
    });
}

// ==================== Auto Refresh ====================
function startAutoRefresh() {
    AdminState.refreshTimers.dashboard = setInterval(() => {
        if (AdminState.currentTab === 'dashboard') {
            loadDashboard();
        }
    }, REFRESH_INTERVAL);
}

function stopAutoRefresh() {
    Object.values(AdminState.refreshTimers).forEach(timer => clearInterval(timer));
}

// Cleanup on page unload
window.addEventListener('beforeunload', stopAutoRefresh);
