/**
 * OCR Version Management Module
 * Handles version listing, comparison, and rollback
 *
 * Features:
 * - Version history display
 * - Side-by-side and unified diff comparison
 * - Rollback to previous versions
 * - Version details modal
 */

/**
 * Version Manager singleton
 */
const VersionManager = {
    // State
    currentDocumentId: null,
    versions: [],
    compareMode: false,
    selectedVersions: [],
    diffMode: 'sideBySide', // 'sideBySide' or 'unified'

    /**
     * Initialize version management for a document
     * @param {string} documentId - Document UUID
     */
    async init(documentId) {
        this.currentDocumentId = documentId;
        this.versions = [];
        this.selectedVersions = [];
        this.compareMode = false;
        await this.loadVersions();
        this.showVersionSection();
    },

    /**
     * Show version section in UI
     */
    showVersionSection() {
        const section = document.getElementById('version-section');
        if (section) {
            section.style.display = 'block';
        }
    },

    /**
     * Hide version section
     */
    hideVersionSection() {
        const section = document.getElementById('version-section');
        if (section) {
            section.style.display = 'none';
        }
        this.currentDocumentId = null;
        this.versions = [];
    },

    /**
     * Load versions for the current document
     */
    async loadVersions() {
        if (!this.currentDocumentId) return;

        try {
            const response = await api.get(
                `/documents/${this.currentDocumentId}/versions/`
            );
            this.versions = response.versions || [];
            this.renderVersionList();
        } catch (error) {
            console.error('Fehler beim Laden der Versionen:', error);
            showToast('Fehler beim Laden der Versionen', 'error');
        }
    },

    /**
     * Render version list UI
     */
    renderVersionList() {
        const container = document.getElementById('version-list');
        if (!container) return;

        if (this.versions.length === 0) {
            container.innerHTML = '<p class="no-versions">Keine Versionen vorhanden</p>';
            return;
        }

        container.innerHTML = this.versions.map(version => `
            <div class="version-item ${version.is_current ? 'current' : ''} ${version.is_rollback ? 'rollback' : ''}"
                 data-version="${version.version_number}">
                <div class="version-header">
                    <span class="version-number">Version ${version.version_number}</span>
                    ${version.is_current ? '<span class="badge current">Aktuell</span>' : ''}
                    ${version.is_rollback ? '<span class="badge rollback">Rollback</span>' : ''}
                </div>
                <div class="version-meta">
                    <span class="version-backend">${this.escapeHtml(version.backend)}</span>
                    <span class="version-confidence">
                        Konfidenz: ${version.confidence_score ? (version.confidence_score * 100).toFixed(1) : 0}%
                    </span>
                    <span class="version-date">
                        ${this.formatDate(version.created_at)}
                    </span>
                </div>
                ${version.version_note ?
                    `<div class="version-note">${this.escapeHtml(version.version_note)}</div>` : ''}
                <div class="version-actions">
                    <button class="btn-sm" onclick="VersionManager.viewVersion(${version.version_number})">
                        Anzeigen
                    </button>
                    ${this.compareMode ? `
                        <label class="compare-checkbox">
                            <input type="checkbox"
                                   onchange="VersionManager.toggleVersionSelection(${version.version_number})"
                                   ${this.selectedVersions.includes(version.version_number) ? 'checked' : ''}>
                            Vergleichen
                        </label>
                    ` : ''}
                    ${!version.is_current ? `
                        <button class="btn-sm btn-warning"
                                onclick="VersionManager.rollback(${version.version_number})">
                            Wiederherstellen
                        </button>
                    ` : ''}
                </div>
            </div>
        `).join('');
    },

    /**
     * View a specific version
     * @param {number} versionNumber - Version number to view
     */
    async viewVersion(versionNumber) {
        try {
            const version = await api.get(
                `/documents/${this.currentDocumentId}/versions/${versionNumber}`
            );
            this.showVersionDetails(version);
        } catch (error) {
            console.error('Fehler beim Laden der Version:', error);
            showToast('Fehler beim Laden der Version', 'error');
        }
    },

    /**
     * Show version details in modal
     * @param {Object} version - Version data
     */
    showVersionDetails(version) {
        const modal = document.getElementById('version-modal');
        const content = document.getElementById('version-modal-content');

        if (!modal || !content) return;

        content.innerHTML = `
            <div class="version-detail">
                <h3>Version ${version.version_number}</h3>
                <div class="version-info-grid">
                    <div class="info-item">
                        <label>Backend:</label>
                        <span>${this.escapeHtml(version.backend)}</span>
                    </div>
                    <div class="info-item">
                        <label>Konfidenz:</label>
                        <span>${version.confidence_score ? (version.confidence_score * 100).toFixed(1) : 0}%</span>
                    </div>
                    <div class="info-item">
                        <label>Worter:</label>
                        <span>${version.word_count || 0}</span>
                    </div>
                    <div class="info-item">
                        <label>Zeichen:</label>
                        <span>${version.char_count || 0}</span>
                    </div>
                    <div class="info-item">
                        <label>Erstellt:</label>
                        <span>${this.formatDate(version.created_at)}</span>
                    </div>
                    <div class="info-item">
                        <label>Umlaute:</label>
                        <span>${version.has_umlauts ? 'Ja' : 'Nein'}</span>
                    </div>
                </div>

                <div class="extracted-entities">
                    <h4>Erkannte Entitaten</h4>
                    <div class="entity-list">
                        ${version.detected_dates?.length ?
                            `<div class="entity-group">
                                <label>Datumswerte:</label>
                                <span>${version.detected_dates.map(d => this.escapeHtml(d)).join(', ')}</span>
                            </div>` : ''}
                        ${version.detected_ibans?.length ?
                            `<div class="entity-group">
                                <label>IBANs:</label>
                                <span>${version.detected_ibans.map(i => this.escapeHtml(i)).join(', ')}</span>
                            </div>` : ''}
                        ${version.detected_vat_ids?.length ?
                            `<div class="entity-group">
                                <label>USt-IdNr.:</label>
                                <span>${version.detected_vat_ids.map(v => this.escapeHtml(v)).join(', ')}</span>
                            </div>` : ''}
                    </div>
                </div>

                <div class="version-text">
                    <h4>Extrahierter Text</h4>
                    <pre>${this.escapeHtml(version.extracted_text || 'Kein Text')}</pre>
                </div>
            </div>
        `;

        modal.style.display = 'flex';
    },

    /**
     * Toggle compare mode
     */
    toggleCompareMode() {
        this.compareMode = !this.compareMode;
        this.selectedVersions = [];
        this.renderVersionList();

        const compareBtn = document.getElementById('compare-versions-btn');
        if (compareBtn) {
            compareBtn.textContent = this.compareMode ?
                'Vergleich abbrechen' : 'Versionen vergleichen';
            compareBtn.classList.toggle('active', this.compareMode);
        }
    },

    /**
     * Toggle version selection for comparison
     * @param {number} versionNumber - Version number
     */
    toggleVersionSelection(versionNumber) {
        const index = this.selectedVersions.indexOf(versionNumber);
        if (index > -1) {
            this.selectedVersions.splice(index, 1);
        } else if (this.selectedVersions.length < 2) {
            this.selectedVersions.push(versionNumber);
        } else {
            showToast('Maximal 2 Versionen auswahlen', 'warning');
            return;
        }

        // Auto-compare when 2 versions selected
        if (this.selectedVersions.length === 2) {
            this.compareVersions();
        }
    },

    /**
     * Compare two versions
     */
    async compareVersions() {
        if (this.selectedVersions.length !== 2) {
            showToast('Bitte zwei Versionen auswahlen', 'warning');
            return;
        }

        try {
            const [versionA, versionB] = this.selectedVersions.sort((a, b) => a - b);

            const comparison = await api.post(
                `/documents/${this.currentDocumentId}/versions/compare`,
                { version_a: versionA, version_b: versionB }
            );

            this.showComparison(comparison);
        } catch (error) {
            console.error('Fehler beim Vergleichen:', error);
            showToast('Fehler beim Vergleichen der Versionen', 'error');
        }
    },

    /**
     * Toggle diff display mode
     */
    toggleDiffMode() {
        this.diffMode = this.diffMode === 'sideBySide' ? 'unified' : 'sideBySide';
        const diffContainer = document.querySelector('.diff-container');
        const toggleBtn = document.getElementById('diff-toggle-btn');

        if (diffContainer && this._currentComparison) {
            if (this.diffMode === 'sideBySide' && this._currentComparison.text_diff_html) {
                diffContainer.innerHTML = this._currentComparison.text_diff_html;
            } else if (this._currentComparison.text_diff_unified) {
                diffContainer.innerHTML = `<pre class="unified-diff">${this.escapeHtml(this._currentComparison.text_diff_unified)}</pre>`;
            }
        }

        if (toggleBtn) {
            toggleBtn.textContent = this.diffMode === 'sideBySide' ?
                'Unified Diff anzeigen' : 'Side-by-Side anzeigen';
        }
    },

    /**
     * Show version comparison UI
     * @param {Object} comparison - Comparison data
     */
    showComparison(comparison) {
        this._currentComparison = comparison;

        const modal = document.getElementById('compare-modal');
        const content = document.getElementById('compare-modal-content');

        if (!modal || !content) return;

        const { version_a, version_b, differences, text_diff_html, text_diff_unified } = comparison;

        const diffContent = this.diffMode === 'sideBySide' && text_diff_html
            ? text_diff_html
            : (text_diff_unified ? `<pre class="unified-diff">${this.escapeHtml(text_diff_unified)}</pre>` : '');

        content.innerHTML = `
            <div class="version-compare">
                <h3>Versionsvergleich</h3>

                <div class="compare-summary">
                    <div class="compare-header">
                        <div class="version-col">
                            <h4>Version ${version_a.version_number}</h4>
                            <span class="backend">${this.escapeHtml(version_a.backend)}</span>
                        </div>
                        <div class="version-col">
                            <h4>Version ${version_b.version_number}</h4>
                            <span class="backend">${this.escapeHtml(version_b.backend)}</span>
                        </div>
                    </div>

                    <div class="compare-stats">
                        <div class="stat-row">
                            <span class="label">Konfidenz:</span>
                            <span>${version_a.confidence_score ? (version_a.confidence_score * 100).toFixed(1) : 0}%</span>
                            <span class="delta ${comparison.confidence_delta >= 0 ? 'positive' : 'negative'}">
                                ${comparison.confidence_delta ? ((comparison.confidence_delta >= 0 ? '+' : '') + (comparison.confidence_delta * 100).toFixed(1) + '%') : '-'}
                            </span>
                            <span>${version_b.confidence_score ? (version_b.confidence_score * 100).toFixed(1) : 0}%</span>
                        </div>
                        <div class="stat-row">
                            <span class="label">Worter:</span>
                            <span>${version_a.word_count || 0}</span>
                            <span class="delta ${comparison.word_count_delta >= 0 ? 'positive' : 'negative'}">
                                ${comparison.word_count_delta ? ((comparison.word_count_delta >= 0 ? '+' : '') + comparison.word_count_delta) : '-'}
                            </span>
                            <span>${version_b.word_count || 0}</span>
                        </div>
                        <div class="stat-row">
                            <span class="label">Backend geandert:</span>
                            <span colspan="3">${differences.backend_changed ? 'Ja' : 'Nein'}</span>
                        </div>
                    </div>
                </div>

                ${diffContent ? `
                    <div class="text-diff">
                        <div class="diff-header">
                            <h4>Textunterschiede</h4>
                            <button id="diff-toggle-btn" class="btn-sm" onclick="VersionManager.toggleDiffMode()">
                                ${this.diffMode === 'sideBySide' ? 'Unified Diff anzeigen' : 'Side-by-Side anzeigen'}
                            </button>
                        </div>
                        <div class="diff-container">${diffContent}</div>
                    </div>
                ` : '<p class="no-diff">Kein Textunterschied</p>'}
            </div>
        `;

        modal.style.display = 'flex';
    },

    /**
     * Rollback to a previous version
     * @param {number} targetVersion - Version number to rollback to
     */
    async rollback(targetVersion) {
        const confirmed = confirm(
            `Mochten Sie wirklich zu Version ${targetVersion} zuruckkehren?\n` +
            'Eine neue Version wird erstellt.'
        );

        if (!confirmed) return;

        try {
            const result = await api.post(
                `/documents/${this.currentDocumentId}/versions/rollback`,
                {
                    target_version: targetVersion,
                    rollback_note: `Manueller Rollback zu Version ${targetVersion}`
                }
            );

            showToast(result.message, 'success');
            await this.loadVersions();

        } catch (error) {
            console.error('Fehler beim Rollback:', error);
            showToast('Fehler beim Rollback', 'error');
        }
    },

    /**
     * Close modal by ID
     * @param {string} modalId - Modal element ID
     */
    closeModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.style.display = 'none';
        }
    },

    /**
     * Format date for German locale
     * @param {string} dateStr - ISO date string
     * @returns {string} Formatted date
     */
    formatDate(dateStr) {
        if (!dateStr) return '-';
        try {
            return new Date(dateStr).toLocaleString('de-DE', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            });
        } catch {
            return dateStr;
        }
    },

    /**
     * Escape HTML to prevent XSS
     * @param {string} text - Text to escape
     * @returns {string} Escaped text
     */
    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
};

// Export for global access
window.VersionManager = VersionManager;
