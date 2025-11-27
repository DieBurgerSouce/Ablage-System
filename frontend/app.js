/**
 * Ablage-System OCR Frontend Application
 * GPU-beschleunigte Dokumentenverarbeitung mit Authentifizierung
 *
 * Version: 2.0
 * Features: Authentication, Batch Processing, Real-time Updates, Document History
 */

// ==================== Application State ====================

const AppState = {
    files: [],
    currentProcessing: null,
    processingQueue: [],
    results: {},
    documentHistory: [],
    gpuStatus: null,
    processingTimer: null,
    startTime: null,
    currentUser: null,
    pollingInterval: null,
    uploadProgress: new Map()
};

// ==================== Application Initialization ====================

document.addEventListener('DOMContentLoaded', () => {
    initializeApplication();
});

async function initializeApplication() {
    // Initialize display mode
    initializeDisplayMode();

    // Check authentication
    if (authManager.isAuthenticated()) {
        await loadUserSession();
    } else {
        showAuthUI();
    }

    // Initialize UI components
    initializeDropzone();
    initializeControls();
    initializeTabs();
    initializeAuthUI();

    // Start monitoring
    startGPUMonitoring();
    checkBackendHealth();

    // Listen for auth events
    window.addEventListener('auth:login', handleLoginEvent);
    window.addEventListener('auth:logout', handleLogoutEvent);
}

// ==================== Authentication UI ====================

function initializeAuthUI() {
    // Login form
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        loginForm.addEventListener('submit', handleLogin);
    }

    // Register form
    const registerForm = document.getElementById('register-form');
    if (registerForm) {
        registerForm.addEventListener('submit', handleRegister);
    }

    // Logout button
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', handleLogoutClick);
    }

    // Toggle between login/register
    const showRegisterBtn = document.getElementById('show-register');
    const showLoginBtn = document.getElementById('show-login');

    if (showRegisterBtn) {
        showRegisterBtn.addEventListener('click', () => toggleAuthForms('register'));
    }

    if (showLoginBtn) {
        showLoginBtn.addEventListener('click', () => toggleAuthForms('login'));
    }
}

function toggleAuthForms(form) {
    const loginContainer = document.getElementById('login-container');
    const registerContainer = document.getElementById('register-container');

    if (form === 'register') {
        loginContainer.style.display = 'none';
        registerContainer.style.display = 'block';
    } else {
        loginContainer.style.display = 'block';
        registerContainer.style.display = 'none';
    }
}

async function handleLogin(e) {
    e.preventDefault();

    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;

    try {
        showLoadingState('login-btn', 'Anmelden...');
        await authManager.login(email, password);
        // Success handled by login event
    } catch (error) {
        console.error('Login error:', error);
    } finally {
        hideLoadingState('login-btn', 'Anmelden');
    }
}

async function handleRegister(e) {
    e.preventDefault();

    const email = document.getElementById('register-email').value;
    const username = document.getElementById('register-username').value;
    const password = document.getElementById('register-password').value;
    const confirmPassword = document.getElementById('register-confirm-password').value;
    const fullName = document.getElementById('register-fullname').value;

    // Validate passwords match
    if (password !== confirmPassword) {
        showToast('Passwörter stimmen nicht überein', 'error');
        return;
    }

    // Validate password strength
    const passwordValidation = authManager.validatePassword(password);
    if (!passwordValidation.valid) {
        showToast(passwordValidation.errors[0], 'error');
        return;
    }

    try {
        showLoadingState('register-btn', 'Registrieren...');
        await authManager.register({
            email,
            username,
            password,
            full_name: fullName,
            preferred_language: 'de'
        });

        // Switch to login form
        toggleAuthForms('login');
        document.getElementById('login-email').value = email;
    } catch (error) {
        console.error('Registration error:', error);
    } finally {
        hideLoadingState('register-btn', 'Registrieren');
    }
}

async function handleLogoutClick() {
    if (confirm('Möchten Sie sich wirklich abmelden?')) {
        await authManager.logout();
    }
}

function handleLoginEvent(event) {
    const user = event.detail;
    AppState.currentUser = user;
    hideAuthUI();
    showMainUI();
    loadDocumentHistory();
    showToast(`Willkommen zurück, ${user.username}!`, 'success');
}

function handleLogoutEvent() {
    AppState.currentUser = null;
    AppState.documentHistory = [];
    showAuthUI();
    hideMainUI();
}

async function loadUserSession() {
    try {
        const user = await authManager.getCurrentUserInfo();
        AppState.currentUser = user;
        hideAuthUI();
        showMainUI();
        await loadDocumentHistory();
    } catch (error) {
        // Session invalid, show login
        authManager.handleLogout();
    }
}

function showAuthUI() {
    const authSection = document.getElementById('auth-section');
    if (authSection) {
        authSection.style.display = 'flex';
    }
}

function hideAuthUI() {
    const authSection = document.getElementById('auth-section');
    if (authSection) {
        authSection.style.display = 'none';
    }
}

function showMainUI() {
    const mainContent = document.querySelector('main');
    const userProfileSection = document.getElementById('user-profile-section');

    if (mainContent) {
        mainContent.style.display = 'block';
    }

    if (userProfileSection) {
        userProfileSection.style.display = 'block';
        updateUserProfile();
    }
}

function hideMainUI() {
    const mainContent = document.querySelector('main');
    const userProfileSection = document.getElementById('user-profile-section');

    if (mainContent) {
        mainContent.style.display = 'none';
    }

    if (userProfileSection) {
        userProfileSection.style.display = 'none';
    }
}

function updateUserProfile() {
    const user = AppState.currentUser;
    if (!user) return;

    const usernameElement = document.getElementById('profile-username');
    const emailElement = document.getElementById('profile-email');

    if (usernameElement) {
        usernameElement.textContent = user.username || user.email;
    }

    if (emailElement) {
        emailElement.textContent = user.email;
    }
}

// ==================== Display Mode Management ====================

function initializeDisplayMode() {
    const savedMode = localStorage.getItem('displayMode') || 'dark';
    document.body.setAttribute('data-mode', savedMode);

    const modeBtns = document.querySelectorAll('.mode-btn');
    modeBtns.forEach(btn => {
        if (btn.getAttribute('data-mode') === savedMode) {
            btn.classList.add('active');
        }

        btn.addEventListener('click', () => {
            const mode = btn.getAttribute('data-mode');
            setDisplayMode(mode);
        });
    });
}

function setDisplayMode(mode) {
    document.body.setAttribute('data-mode', mode);
    localStorage.setItem('displayMode', mode);

    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.getAttribute('data-mode') === mode) {
            btn.classList.add('active');
        }
    });

    showToast(`Display-Modus: ${getModeName(mode)}`, 'info');
}

function getModeName(mode) {
    const names = {
        'dark': 'Dunkler Modus',
        'light': 'Heller Modus',
        'whitescreen': 'Hoher Kontrast',
        'blackscreen': 'Invertierter Kontrast'
    };
    return names[mode] || mode;
}

// ==================== GPU Monitoring ====================

async function startGPUMonitoring() {
    updateGPUStatus();
    setInterval(updateGPUStatus, 2000);
}

async function updateGPUStatus() {
    try {
        const data = await api.get('/gpu/status', { includeApiVersion: false });
        AppState.gpuStatus = data;

        const gpuNameEl = document.getElementById('gpu-name');
        const vramUsageEl = document.getElementById('vram-usage');
        const gpuIndicator = document.getElementById('gpu-indicator');

        if (gpuNameEl) {
            gpuNameEl.textContent = data.device_name || 'Nicht verfügbar';
        }

        if (vramUsageEl) {
            const memoryGB = data.memory_used ? (data.memory_used / (1024 ** 3)).toFixed(1) : '0.0';
            vramUsageEl.textContent = memoryGB;
        }

        if (gpuIndicator) {
            gpuIndicator.className = 'gpu-indicator';
            gpuIndicator.classList.add(data.available ? 'gpu-active' : 'gpu-inactive');
        }

        if (AppState.currentProcessing) {
            const gpuUsageEl = document.getElementById('gpu-usage');
            if (gpuUsageEl && data.utilization !== undefined) {
                gpuUsageEl.textContent = `${data.utilization}%`;
            }
        }

    } catch (error) {
        console.error('GPU status error:', error);
        setGPUOffline();
    }
}

function setGPUOffline() {
    const gpuNameEl = document.getElementById('gpu-name');
    const vramUsageEl = document.getElementById('vram-usage');
    const gpuIndicator = document.getElementById('gpu-indicator');

    if (gpuNameEl) gpuNameEl.textContent = 'Offline';
    if (vramUsageEl) vramUsageEl.textContent = '0.0';
    if (gpuIndicator) {
        gpuIndicator.className = 'gpu-indicator gpu-inactive';
    }
}

// ==================== Backend Health Check ====================

async function checkBackendHealth() {
    try {
        const data = await api.get('/health', { includeApiVersion: false });
        console.log('Backend health:', data);

        const backendInfo = document.getElementById('backend-info');
        if (backendInfo && data.components?.ocr) {
            const backends = data.components.ocr.backends || [];
            backendInfo.textContent = `Backend: ${backends.join(', ') || 'Keine'}`;
        }
    } catch (error) {
        console.error('Health check failed:', error);
        showToast('Backend nicht erreichbar', 'error');
    }
}

// ==================== File Upload & Dropzone ====================

function initializeDropzone() {
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('file-input');

    if (!dropzone || !fileInput) return;

    dropzone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => handleFiles(e.target.files));

    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.add('dragover');
    });

    dropzone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.remove('dragover');
    });

    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.remove('dragover');
        handleFiles(e.dataTransfer.files);
    });
}

function handleFiles(files) {
    const validFiles = [];
    const allowedTypes = ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.tif', '.bmp'];

    for (let file of files) {
        const ext = '.' + file.name.split('.').pop().toLowerCase();
        if (allowedTypes.includes(ext)) {
            validFiles.push(file);
        } else {
            showToast(`Dateiformat nicht unterstützt: ${file.name}`, 'warning');
        }
    }

    if (validFiles.length > 0) {
        AppState.files = AppState.files.concat(validFiles);
        updateFileQueue();
        updateProcessButton();
    }
}

function updateFileQueue() {
    const queueSection = document.getElementById('queue-section');
    const fileQueue = document.getElementById('file-queue');

    if (!fileQueue) return;

    if (AppState.files.length > 0) {
        if (queueSection) queueSection.style.display = 'block';

        fileQueue.innerHTML = AppState.files.map((file, index) => `
            <div class="file-item" data-index="${index}">
                <div class="file-info">
                    <span class="file-icon">📄</span>
                    <span class="file-name">${escapeHtml(file.name)}</span>
                    <span class="file-size">${formatFileSize(file.size)}</span>
                </div>
                <div class="file-actions">
                    <div class="upload-progress" id="progress-${index}" style="display: none;">
                        <div class="upload-progress-bar" id="progress-bar-${index}"></div>
                    </div>
                    <button class="remove-file" onclick="removeFile(${index})" aria-label="Datei entfernen">×</button>
                </div>
            </div>
        `).join('');
    } else {
        if (queueSection) queueSection.style.display = 'none';
    }
}

function removeFile(index) {
    AppState.files.splice(index, 1);
    updateFileQueue();
    updateProcessButton();
}

function updateProcessButton() {
    const processBtn = document.getElementById('process-btn');
    const processText = document.getElementById('process-text');

    if (!processBtn || !processText) return;

    if (AppState.files.length > 0) {
        processBtn.disabled = false;
        const fileText = AppState.files.length === 1 ? 'Datei' : 'Dateien';
        processText.textContent = `Verarbeiten (${AppState.files.length} ${fileText})`;
    } else {
        processBtn.disabled = true;
        processText.textContent = 'Datei auswählen';
    }
}

// ==================== OCR Processing ====================

function initializeControls() {
    const processBtn = document.getElementById('process-btn');
    if (processBtn) {
        processBtn.addEventListener('click', startProcessing);
    }

    // Result actions
    const copyBtn = document.getElementById('copy-text');
    const downloadBtn = document.getElementById('download-text');
    const validateBtn = document.getElementById('validate-text');

    if (copyBtn) copyBtn.addEventListener('click', copyExtractedText);
    if (downloadBtn) downloadBtn.addEventListener('click', downloadExtractedText);
    if (validateBtn) validateBtn.addEventListener('click', validateExtractedText);
}

async function startProcessing() {
    if (AppState.files.length === 0) return;

    // Check authentication
    if (!authManager.isAuthenticated()) {
        showToast('Bitte melden Sie sich an, um Dokumente zu verarbeiten', 'warning');
        return;
    }

    const backend = document.getElementById('backend')?.value || 'auto';
    const language = document.getElementById('language')?.value || 'de';
    const detectLayout = document.getElementById('detect-layout')?.checked ?? true;

    // Show progress section
    const progressSection = document.getElementById('progress-section');
    const resultsSection = document.getElementById('results-section');

    if (progressSection) progressSection.style.display = 'block';
    if (resultsSection) resultsSection.style.display = 'none';

    // Initialize progress
    AppState.startTime = Date.now();
    AppState.processingTimer = setInterval(updateProcessingTime, 100);

    const totalDocsEl = document.getElementById('total-docs');
    if (totalDocsEl) totalDocsEl.textContent = AppState.files.length;

    // Disable process button
    const processBtn = document.getElementById('process-btn');
    if (processBtn) processBtn.disabled = true;

    // Process files
    const results = [];
    for (let i = 0; i < AppState.files.length; i++) {
        const file = AppState.files[i];
        AppState.currentProcessing = file;

        const currentDocEl = document.getElementById('current-doc');
        if (currentDocEl) currentDocEl.textContent = i + 1;

        updateProgress((i / AppState.files.length) * 100);

        try {
            const result = await processFile(file, {
                backend,
                language,
                detect_layout: detectLayout
            }, i);

            results.push(result);
            AppState.results[file.name] = result;
            showToast(`✓ ${file.name} erfolgreich verarbeitet`, 'success');

        } catch (error) {
            console.error(`Error processing ${file.name}:`, error);
            showToast(`✗ Fehler bei ${file.name}: ${error.message}`, 'error');
            results.push({
                filename: file.name,
                success: false,
                error: error.message
            });
        }
    }

    // Processing complete
    clearInterval(AppState.processingTimer);
    updateProgress(100);

    // Show results after brief delay
    setTimeout(() => {
        showResults();
        loadDocumentHistory(); // Refresh history
    }, 500);
}

async function processFile(file, options, fileIndex) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('backend', options.backend);
    formData.append('language', options.language);
    formData.append('detect_layout', options.detect_layout);

    // Show upload progress
    const progressBar = document.getElementById(`progress-${fileIndex}`);
    const progressFill = document.getElementById(`progress-bar-${fileIndex}`);

    if (progressBar) progressBar.style.display = 'block';

    return api.upload('/ocr/process', file, {
        fields: {
            backend: options.backend,
            language: options.language,
            detect_layout: options.detect_layout
        },
        includeApiVersion: false,
        onProgress: (percent) => {
            if (progressFill) {
                progressFill.style.width = `${percent}%`;
            }
        }
    });
}

function updateProgress(percentage) {
    const progressFill = document.getElementById('progress-fill');
    if (progressFill) {
        progressFill.style.width = `${percentage}%`;
    }
}

function updateProcessingTime() {
    if (AppState.startTime) {
        const elapsed = (Date.now() - AppState.startTime) / 1000;
        const timeEl = document.getElementById('processing-time');
        if (timeEl) {
            timeEl.textContent = `${elapsed.toFixed(1)}s`;
        }
    }
}

// ==================== Results Display ====================

function showResults() {
    const progressSection = document.getElementById('progress-section');
    const resultsSection = document.getElementById('results-section');

    if (progressSection) progressSection.style.display = 'none';
    if (resultsSection) resultsSection.style.display = 'block';

    const allTexts = [];
    let totalConfidence = 0;
    let validResults = 0;

    Object.entries(AppState.results).forEach(([filename, result]) => {
        if (result.success && result.text) {
            allTexts.push(`--- ${filename} ---\n${result.text}`);
            if (result.confidence !== undefined) {
                totalConfidence += result.confidence;
                validResults++;
            }
        }
    });

    // Display text
    const textDisplay = document.getElementById('extracted-text');
    if (textDisplay) {
        textDisplay.textContent = allTexts.join('\n\n') || 'Kein Text extrahiert';
    }

    // Update confidence
    if (validResults > 0) {
        const avgConfidence = totalConfidence / validResults;
        updateConfidence(avgConfidence);
    }

    // Update metadata and statistics
    updateMetadata();
    updateStatistics();
    updateBackendInfo();

    // Clear processing state
    AppState.currentProcessing = null;
    AppState.files = [];
    updateFileQueue();
    updateProcessButton();
}

function updateConfidence(confidence) {
    const fill = document.getElementById('confidence-fill');
    const value = document.getElementById('confidence-value');

    if (!fill || !value) return;

    fill.style.width = `${confidence}%`;
    value.textContent = `${confidence.toFixed(1)}%`;

    if (confidence >= 90) {
        fill.style.backgroundColor = '#10b981';
    } else if (confidence >= 75) {
        fill.style.backgroundColor = '#f59e0b';
    } else {
        fill.style.backgroundColor = '#ef4444';
    }
}

function updateMetadata() {
    const metadataDisplay = document.getElementById('metadata-display');
    if (!metadataDisplay) return;

    const results = Object.entries(AppState.results);
    const metadata = results.map(([filename, result]) => {
        if (result.metadata) {
            return `
                <div class="metadata-item">
                    <h4>${escapeHtml(filename)}</h4>
                    <dl>
                        ${Object.entries(result.metadata).map(([key, value]) => `
                            <dt>${escapeHtml(key)}:</dt>
                            <dd>${escapeHtml(String(value))}</dd>
                        `).join('')}
                    </dl>
                </div>
            `;
        }
        return '';
    }).filter(Boolean).join('');

    metadataDisplay.innerHTML = metadata || '<p class="no-data">Keine Metadaten verfügbar</p>';
}

function updateStatistics() {
    const statsDisplay = document.getElementById('stats-display');
    if (!statsDisplay) return;

    const results = Object.entries(AppState.results);
    let totalChars = 0;
    let totalTime = 0;
    let successCount = 0;
    let errorCount = 0;

    results.forEach(([, result]) => {
        if (result.success) {
            successCount++;
            if (result.text) totalChars += result.text.length;
            if (result.processing_time) totalTime += result.processing_time;
        } else {
            errorCount++;
        }
    });

    const avgTime = results.length > 0 ? (totalTime / results.length).toFixed(2) : 0;
    const processingTime = AppState.startTime ?
        ((Date.now() - AppState.startTime) / 1000).toFixed(1) : 0;

    statsDisplay.innerHTML = `
        <div class="stat-item">
            <span class="stat-label">Dokumente verarbeitet:</span>
            <span class="stat-value">${results.length}</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">Erfolgreich:</span>
            <span class="stat-value">${successCount}</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">Fehler:</span>
            <span class="stat-value">${errorCount}</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">Gesamtzeit:</span>
            <span class="stat-value">${processingTime}s</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">Durchschnitt/Dokument:</span>
            <span class="stat-value">${avgTime}s</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">Zeichen extrahiert:</span>
            <span class="stat-value">${totalChars.toLocaleString('de-DE')}</span>
        </div>
    `;
}

function updateBackendInfo() {
    const speedElement = document.getElementById('processing-speed');
    if (!speedElement) return;

    if (AppState.gpuStatus?.available) {
        speedElement.textContent = 'Geschwindigkeit: GPU-beschleunigt';
    } else {
        speedElement.textContent = 'Geschwindigkeit: CPU-Modus';
    }
}

// ==================== Tabs ====================

function initializeTabs() {
    const tabButtons = document.querySelectorAll('.tab-btn');

    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.dataset.tab;

            tabButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.remove('active');
            });

            const targetContent = document.getElementById(`${targetTab}-tab`);
            if (targetContent) {
                targetContent.classList.add('active');
            }
        });
    });
}

// ==================== Result Actions ====================

function copyExtractedText() {
    const textDisplay = document.getElementById('extracted-text');
    if (!textDisplay) return;

    const text = textDisplay.textContent;
    navigator.clipboard.writeText(text).then(() => {
        showToast('Text in Zwischenablage kopiert', 'success');
    }).catch(err => {
        console.error('Failed to copy:', err);
        showToast('Kopieren fehlgeschlagen', 'error');
    });
}

function downloadExtractedText() {
    const textDisplay = document.getElementById('extracted-text');
    if (!textDisplay) return;

    const text = textDisplay.textContent;
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ocr-ergebnis-${Date.now()}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast('Text gespeichert', 'success');
}

async function validateExtractedText() {
    const textDisplay = document.getElementById('extracted-text');
    if (!textDisplay) return;

    const text = textDisplay.textContent;

    try {
        const validation = await api.post('/ocr/test', { text }, {
            includeApiVersion: false
        });

        let message = 'Validierung abgeschlossen:\n';
        message += `- Gültiges Deutsch: ${validation.valid_german ? 'Ja' : 'Nein'}\n`;
        message += `- Umlaute gefunden: ${validation.has_umlauts ? 'Ja' : 'Nein'}\n`;
        message += `- Datumswerte: ${validation.dates?.length || 0}\n`;
        message += `- Währungsbeträge: ${validation.amounts?.length || 0}\n`;

        showToast(message, 'info');
    } catch (error) {
        console.error('Validation error:', error);
        showToast('Validierung fehlgeschlagen', 'error');
    }
}

// ==================== Document History ====================

async function loadDocumentHistory() {
    // This would call a backend endpoint to get document history
    // For now, we'll use localStorage as a fallback
    try {
        const history = localStorage.getItem('documentHistory');
        if (history) {
            AppState.documentHistory = JSON.parse(history);
            updateDocumentHistoryUI();
        }
    } catch (error) {
        console.error('Error loading document history:', error);
    }
}

function updateDocumentHistoryUI() {
    const historyContainer = document.getElementById('document-history');
    if (!historyContainer) return;

    if (AppState.documentHistory.length === 0) {
        historyContainer.innerHTML = '<p class="no-data">Keine Dokumente verarbeitet</p>';
        return;
    }

    historyContainer.innerHTML = AppState.documentHistory.map(doc => `
        <div class="history-item">
            <div class="history-info">
                <span class="history-name">${escapeHtml(doc.filename)}</span>
                <span class="history-date">${new Date(doc.timestamp).toLocaleString('de-DE')}</span>
            </div>
            <div class="history-meta">
                <span class="history-backend">${doc.backend}</span>
                <span class="history-status ${doc.success ? 'success' : 'error'}">
                    ${doc.success ? '✓' : '✗'}
                </span>
            </div>
        </div>
    `).join('');
}

// ==================== Utility Functions ====================

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    container.appendChild(toast);

    setTimeout(() => toast.classList.add('show'), 10);

    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => container.removeChild(toast), 300);
    }, 3000);
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showLoadingState(elementId, text) {
    const element = document.getElementById(elementId);
    if (element) {
        element.disabled = true;
        element.dataset.originalText = element.textContent;
        element.textContent = text;
    }
}

function hideLoadingState(elementId, text) {
    const element = document.getElementById(elementId);
    if (element) {
        element.disabled = false;
        element.textContent = text || element.dataset.originalText || 'Submit';
    }
}

// ==================== Export for Debugging ====================

window.AppState = AppState;
window.showToast = showToast;
window.removeFile = removeFile;
