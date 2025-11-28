/**
 * Ablage-System Document Search Module
 * Full-text, semantic, and hybrid search with batch operations
 *
 * Version: 1.0
 * Features: FTS, Semantic Search, Hybrid Search, Similar Documents, Batch Operations
 */

// ==================== Search State ====================

const SearchState = {
    query: '',
    searchType: 'hybrid',
    results: [],
    totalResults: 0,
    currentPage: 1,
    perPage: 20,
    filters: {
        documentType: null,
        status: null,
        dateFrom: null,
        dateTo: null,
        confidenceMin: null,
        hasEmbedding: null,
        language: null,
        tags: null
    },
    sortBy: 'relevance',
    sortOrder: 'desc',
    isLoading: false,
    selectedDocuments: new Set(),
    similarDocuments: [],
    searchHistory: [],
    analyticsId: null,  // Track current search for click analytics
    sessionId: null     // Session ID for analytics grouping
};

// ==================== Utility Functions ====================

/**
 * Sanitize highlight HTML while preserving <mark> tags.
 * Prevents XSS from document content while keeping search highlighting.
 *
 * Sicherheitshinweis: Verwendet kryptografische Platzhalter um
 * Injection-Angriffe mit vorhandenen Platzhalter-Texten zu verhindern.
 */
function sanitizeHighlight(html) {
    if (!html) return '';

    // Einzigartige Platzhalter die nicht in regulaerem Text vorkommen
    const startPlaceholder = '\u0000__MARK_S__\u0000';
    const endPlaceholder = '\u0000__MARK_E__\u0000';

    // Pruefe ob Platzhalter im Input vorkommen (Sicherheitscheck)
    if (html.includes(startPlaceholder) || html.includes(endPlaceholder)) {
        // Fallback: Escape alles und entferne mark tags komplett
        console.warn('Potentieller XSS-Versuch erkannt, Highlights deaktiviert');
        return escapeHtml(html.replace(/<\/?mark>/gi, ''));
    }

    // Replace mark tags with secure placeholders
    const withPlaceholders = html
        .replace(/<mark>/gi, startPlaceholder)
        .replace(/<\/mark>/gi, endPlaceholder);

    // Escape remaining HTML
    const escaped = escapeHtml(withPlaceholders);

    // Restore mark tags
    return escaped
        .replace(new RegExp(escapeRegExp(startPlaceholder), 'g'), '<mark>')
        .replace(new RegExp(escapeRegExp(endPlaceholder), 'g'), '</mark>');
}

/**
 * Escape special regex characters in a string.
 */
function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// ==================== Search Initialization ====================

function initializeSearch() {
    // Initialize search input
    const searchInput = document.getElementById('search-input');
    const searchForm = document.getElementById('search-form');

    if (searchInput) {
        // Debounced search on input
        let debounceTimer;
        searchInput.addEventListener('input', (e) => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                SearchState.query = e.target.value;
                if (SearchState.query.length >= 2) {
                    performSearch();
                }
            }, 300);
        });
    }

    if (searchForm) {
        searchForm.addEventListener('submit', (e) => {
            e.preventDefault();
            performSearch();
        });
    }

    // Initialize search type selector
    const searchTypeSelect = document.getElementById('search-type');
    if (searchTypeSelect) {
        searchTypeSelect.addEventListener('change', (e) => {
            SearchState.searchType = e.target.value;
            if (SearchState.query) {
                performSearch();
            }
        });
    }

    // Initialize filters
    initializeFilters();

    // Initialize batch operations
    initializeBatchOperations();

    // Initialize sorting
    initializeSorting();
}

// ==================== Search Operations ====================

/**
 * Perform search with current state
 */
async function performSearch() {
    if (!SearchState.query || SearchState.query.length < 2) {
        showToast('Bitte mindestens 2 Zeichen eingeben', 'warning');
        return;
    }

    if (!authManager.isAuthenticated()) {
        showToast('Bitte melden Sie sich an, um zu suchen', 'warning');
        return;
    }

    SearchState.isLoading = true;
    updateSearchUI('loading');

    // Generate session ID if not exists
    if (!SearchState.sessionId) {
        SearchState.sessionId = 'sess_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    try {
        // Build query parameters
        const params = new URLSearchParams({
            q: SearchState.query,
            search_type: SearchState.searchType,
            page: SearchState.currentPage,
            per_page: SearchState.perPage,
            sort_by: SearchState.sortBy,
            sort_order: SearchState.sortOrder,
            highlight: 'true',
            session_id: SearchState.sessionId
        });

        // Add filters
        if (SearchState.filters.documentType) {
            params.append('document_type', SearchState.filters.documentType);
        }
        if (SearchState.filters.status) {
            params.append('status', SearchState.filters.status);
        }
        if (SearchState.filters.dateFrom) {
            params.append('date_from', SearchState.filters.dateFrom);
        }
        if (SearchState.filters.dateTo) {
            params.append('date_to', SearchState.filters.dateTo);
        }
        if (SearchState.filters.confidenceMin !== null) {
            params.append('confidence_min', SearchState.filters.confidenceMin);
        }
        if (SearchState.filters.hasEmbedding !== null) {
            params.append('has_embedding', SearchState.filters.hasEmbedding);
        }
        if (SearchState.filters.tags && SearchState.filters.tags.length > 0) {
            SearchState.filters.tags.forEach(tag => params.append('tags', tag));
        }

        const response = await api.get(`/documents/search/?${params.toString()}`);

        SearchState.results = response.results || [];
        SearchState.totalResults = response.total || 0;
        SearchState.analyticsId = response.analytics_id || null;

        // Add to search history
        addToSearchHistory(SearchState.query, SearchState.searchType, SearchState.totalResults);

        updateSearchUI('results');

    } catch (error) {
        console.error('Suchfehler:', error);
        showToast(`Suche fehlgeschlagen: ${error.message}`, 'error');
        updateSearchUI('error');
    } finally {
        SearchState.isLoading = false;
    }
}

/**
 * Get similar documents for a specific document
 */
async function findSimilarDocuments(documentId, options = {}) {
    if (!authManager.isAuthenticated()) {
        showToast('Bitte melden Sie sich an', 'warning');
        return [];
    }

    try {
        const params = new URLSearchParams({
            limit: options.limit || 10,
            similarity_threshold: options.threshold || 0.6,
            exclude_same_type: options.excludeSameType || false
        });

        const response = await api.get(`/documents/${documentId}/similar?${params.toString()}`);
        SearchState.similarDocuments = response || [];

        return SearchState.similarDocuments;

    } catch (error) {
        console.error('Fehler bei aehnlichen Dokumenten:', error);
        showToast(`Aehnliche Dokumente konnten nicht geladen werden: ${error.message}`, 'error');
        return [];
    }
}

/**
 * Get single document details
 */
async function getDocumentDetails(documentId) {
    if (!authManager.isAuthenticated()) {
        showToast('Bitte melden Sie sich an', 'warning');
        return null;
    }

    try {
        return await api.get(`/documents/${documentId}`);
    } catch (error) {
        console.error('Dokumentdetails-Fehler:', error);
        showToast(`Dokument konnte nicht geladen werden: ${error.message}`, 'error');
        return null;
    }
}

/**
 * List documents with pagination and filters
 */
async function listDocuments(options = {}) {
    if (!authManager.isAuthenticated()) {
        showToast('Bitte melden Sie sich an', 'warning');
        return { results: [], total: 0 };
    }

    try {
        const params = new URLSearchParams({
            page: options.page || 1,
            per_page: options.perPage || 20,
            sort_by: options.sortBy || 'created_at',
            sort_order: options.sortOrder || 'desc'
        });

        // Add filters
        if (options.documentType) params.append('document_type', options.documentType);
        if (options.status) params.append('status', options.status);
        if (options.dateFrom) params.append('date_from', options.dateFrom);
        if (options.dateTo) params.append('date_to', options.dateTo);
        if (options.confidenceMin) params.append('confidence_min', options.confidenceMin);
        if (options.hasEmbedding !== undefined) params.append('has_embedding', options.hasEmbedding);
        if (options.language) params.append('language', options.language);

        return await api.get(`/documents/?${params.toString()}`);

    } catch (error) {
        console.error('Dokumentliste-Fehler:', error);
        showToast(`Dokumente konnten nicht geladen werden: ${error.message}`, 'error');
        return { results: [], total: 0 };
    }
}

// ==================== Filter Management ====================

function initializeFilters() {
    // Document type filter
    const typeFilter = document.getElementById('filter-document-type');
    if (typeFilter) {
        typeFilter.addEventListener('change', (e) => {
            SearchState.filters.documentType = e.target.value || null;
            SearchState.currentPage = 1;
            if (SearchState.query) performSearch();
        });
    }

    // Status filter
    const statusFilter = document.getElementById('filter-status');
    if (statusFilter) {
        statusFilter.addEventListener('change', (e) => {
            SearchState.filters.status = e.target.value || null;
            SearchState.currentPage = 1;
            if (SearchState.query) performSearch();
        });
    }

    // Date filters
    const dateFromFilter = document.getElementById('filter-date-from');
    const dateToFilter = document.getElementById('filter-date-to');

    if (dateFromFilter) {
        dateFromFilter.addEventListener('change', (e) => {
            SearchState.filters.dateFrom = e.target.value || null;
            SearchState.currentPage = 1;
            if (SearchState.query) performSearch();
        });
    }

    if (dateToFilter) {
        dateToFilter.addEventListener('change', (e) => {
            SearchState.filters.dateTo = e.target.value || null;
            SearchState.currentPage = 1;
            if (SearchState.query) performSearch();
        });
    }

    // Confidence filter
    const confidenceFilter = document.getElementById('filter-confidence');
    if (confidenceFilter) {
        confidenceFilter.addEventListener('input', (e) => {
            const value = e.target.value ? parseFloat(e.target.value) : null;
            SearchState.filters.confidenceMin = value;
            // Update display
            const display = document.getElementById('confidence-filter-value');
            if (display) display.textContent = value ? `${value}%` : 'Alle';
        });

        confidenceFilter.addEventListener('change', () => {
            SearchState.currentPage = 1;
            if (SearchState.query) performSearch();
        });
    }

    // Tags filter
    const tagsFilter = document.getElementById('filter-tags');
    if (tagsFilter) {
        tagsFilter.addEventListener('change', (e) => {
            const value = e.target.value.trim();
            SearchState.filters.tags = value ? value.split(',').map(t => t.trim()).filter(t => t) : null;
            SearchState.currentPage = 1;
            if (SearchState.query) performSearch();
        });
    }

    // Clear filters button
    const clearFiltersBtn = document.getElementById('clear-filters');
    if (clearFiltersBtn) {
        clearFiltersBtn.addEventListener('click', clearFilters);
    }
}

function clearFilters() {
    SearchState.filters = {
        documentType: null,
        status: null,
        dateFrom: null,
        dateTo: null,
        confidenceMin: null,
        hasEmbedding: null,
        language: null,
        tags: null
    };

    // Reset UI
    const filterElements = document.querySelectorAll('[id^="filter-"]');
    filterElements.forEach(el => {
        if (el.tagName === 'SELECT') el.value = '';
        else if (el.tagName === 'INPUT') el.value = '';
    });

    SearchState.currentPage = 1;
    if (SearchState.query) performSearch();
    showToast('Filter zurueckgesetzt', 'info');
}

// ==================== Sorting ====================

function initializeSorting() {
    const sortSelect = document.getElementById('sort-by');
    const orderSelect = document.getElementById('sort-order');

    if (sortSelect) {
        sortSelect.addEventListener('change', (e) => {
            SearchState.sortBy = e.target.value;
            if (SearchState.query) performSearch();
        });
    }

    if (orderSelect) {
        orderSelect.addEventListener('change', (e) => {
            SearchState.sortOrder = e.target.value;
            if (SearchState.query) performSearch();
        });
    }
}

// ==================== Batch Operations ====================

function initializeBatchOperations() {
    // Select all checkbox
    const selectAllCheckbox = document.getElementById('select-all-documents');
    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('change', (e) => {
            toggleSelectAll(e.target.checked);
        });
    }

    // Batch delete button
    const batchDeleteBtn = document.getElementById('batch-delete');
    if (batchDeleteBtn) {
        batchDeleteBtn.addEventListener('click', showBatchDeleteConfirm);
    }

    // Batch tag button
    const batchTagBtn = document.getElementById('batch-tag');
    if (batchTagBtn) {
        batchTagBtn.addEventListener('click', showBatchTagDialog);
    }

    // Batch export button
    const batchExportBtn = document.getElementById('batch-export');
    if (batchExportBtn) {
        batchExportBtn.addEventListener('click', showBatchExportDialog);
    }
}

function toggleSelectAll(selected) {
    if (selected) {
        SearchState.results.forEach(doc => SearchState.selectedDocuments.add(doc.document_id));
    } else {
        SearchState.selectedDocuments.clear();
    }
    updateSelectionUI();
}

function toggleDocumentSelection(documentId) {
    if (SearchState.selectedDocuments.has(documentId)) {
        SearchState.selectedDocuments.delete(documentId);
    } else {
        SearchState.selectedDocuments.add(documentId);
    }
    updateSelectionUI();
}

function updateSelectionUI() {
    const count = SearchState.selectedDocuments.size;

    // Update selection count display
    const countDisplay = document.getElementById('selected-count');
    if (countDisplay) {
        countDisplay.textContent = count;
    }

    // Enable/disable batch operation buttons
    const batchButtons = document.querySelectorAll('.batch-operation-btn');
    batchButtons.forEach(btn => {
        btn.disabled = count === 0;
    });

    // Update batch actions visibility
    const batchActions = document.getElementById('batch-actions');
    if (batchActions) {
        batchActions.style.display = count > 0 ? 'flex' : 'none';
    }

    // Update individual checkboxes
    document.querySelectorAll('.document-checkbox').forEach(checkbox => {
        const docId = checkbox.dataset.documentId;
        checkbox.checked = SearchState.selectedDocuments.has(docId);
    });
}

/**
 * Batch delete documents
 */
async function batchDeleteDocuments() {
    const documentIds = Array.from(SearchState.selectedDocuments);

    if (documentIds.length === 0) {
        showToast('Keine Dokumente ausgewaehlt', 'warning');
        return;
    }

    try {
        const response = await api.post('/documents/batch/delete', {
            document_ids: documentIds,
            confirm: true
        });

        showToast(
            `${response.processed} Dokumente geloescht (${response.failed} fehlgeschlagen)`,
            response.failed > 0 ? 'warning' : 'success'
        );

        // Clear selection and refresh
        SearchState.selectedDocuments.clear();
        updateSelectionUI();
        performSearch();

    } catch (error) {
        console.error('Batch-Loeschung-Fehler:', error);
        showToast(`Loeschen fehlgeschlagen: ${error.message}`, 'error');
    }
}

/**
 * Batch tag documents
 */
async function batchTagDocuments(tags, operation = 'add') {
    const documentIds = Array.from(SearchState.selectedDocuments);

    if (documentIds.length === 0) {
        showToast('Keine Dokumente ausgewaehlt', 'warning');
        return;
    }

    try {
        const response = await api.post('/documents/batch/tag', {
            document_ids: documentIds,
            tags: tags,
            operation: operation
        });

        showToast(
            `Tags fuer ${response.processed} Dokumente aktualisiert`,
            'success'
        );

        // Refresh search results
        performSearch();

    } catch (error) {
        console.error('Batch-Tagging-Fehler:', error);
        showToast(`Tagging fehlgeschlagen: ${error.message}`, 'error');
    }
}

/**
 * Batch export documents
 */
async function batchExportDocuments(format = 'json', includeText = true, includeMetadata = true) {
    const documentIds = Array.from(SearchState.selectedDocuments);

    if (documentIds.length === 0) {
        showToast('Keine Dokumente ausgewaehlt', 'warning');
        return;
    }

    try {
        // For exports, we need to handle the file download
        const response = await fetch(`${api.baseURL}${api.apiVersion}/documents/batch/export`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            },
            body: JSON.stringify({
                document_ids: documentIds,
                format: format,
                include_text: includeText,
                include_metadata: includeMetadata
            })
        });

        if (!response.ok) {
            throw new Error('Export fehlgeschlagen');
        }

        // Get filename from header or generate one
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = `export.${format}`;
        if (contentDisposition) {
            const match = contentDisposition.match(/filename="(.+)"/);
            if (match) filename = match[1];
        }

        // Download the file
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        showToast(`${documentIds.length} Dokumente exportiert`, 'success');

    } catch (error) {
        console.error('Batch-Export-Fehler:', error);
        showToast(`Export fehlgeschlagen: ${error.message}`, 'error');
    }
}

// ==================== Dialog Functions ====================

function showBatchDeleteConfirm() {
    const count = SearchState.selectedDocuments.size;
    const confirmed = confirm(
        `Moechten Sie wirklich ${count} Dokument(e) loeschen?\nDiese Aktion kann nicht rueckgaengig gemacht werden.`
    );

    if (confirmed) {
        batchDeleteDocuments();
    }
}

function showBatchTagDialog() {
    const dialog = document.getElementById('batch-tag-dialog');
    if (dialog) {
        dialog.style.display = 'flex';
    }
}

function hideBatchTagDialog() {
    const dialog = document.getElementById('batch-tag-dialog');
    if (dialog) {
        dialog.style.display = 'none';
    }
}

function submitBatchTag() {
    const tagsInput = document.getElementById('batch-tags-input');
    const operationSelect = document.getElementById('batch-tag-operation');

    if (!tagsInput) return;

    const tags = tagsInput.value.split(',').map(t => t.trim()).filter(t => t);
    const operation = operationSelect?.value || 'add';

    if (tags.length === 0) {
        showToast('Bitte mindestens einen Tag eingeben', 'warning');
        return;
    }

    hideBatchTagDialog();
    batchTagDocuments(tags, operation);
}

function showBatchExportDialog() {
    const dialog = document.getElementById('batch-export-dialog');
    if (dialog) {
        dialog.style.display = 'flex';
    }
}

function hideBatchExportDialog() {
    const dialog = document.getElementById('batch-export-dialog');
    if (dialog) {
        dialog.style.display = 'none';
    }
}

function submitBatchExport() {
    const formatSelect = document.getElementById('export-format');
    const includeTextCheckbox = document.getElementById('export-include-text');
    const includeMetadataCheckbox = document.getElementById('export-include-metadata');

    const format = formatSelect?.value || 'json';
    const includeText = includeTextCheckbox?.checked ?? true;
    const includeMetadata = includeMetadataCheckbox?.checked ?? true;

    hideBatchExportDialog();
    batchExportDocuments(format, includeText, includeMetadata);
}

// ==================== UI Update Functions ====================

function updateSearchUI(state) {
    const searchResults = document.getElementById('search-results');
    const searchLoading = document.getElementById('search-loading');
    const searchEmpty = document.getElementById('search-empty');
    const searchError = document.getElementById('search-error');
    const resultCount = document.getElementById('result-count');
    const searchInfo = document.getElementById('search-info');

    // Hide all states
    [searchResults, searchLoading, searchEmpty, searchError].forEach(el => {
        if (el) el.style.display = 'none';
    });

    switch (state) {
        case 'loading':
            if (searchLoading) searchLoading.style.display = 'block';
            break;

        case 'results':
            if (SearchState.results.length > 0) {
                if (searchResults) {
                    searchResults.style.display = 'block';
                    renderSearchResults();
                }
                if (resultCount) {
                    resultCount.textContent = SearchState.totalResults;
                }
                if (searchInfo) {
                    searchInfo.style.display = 'flex';
                }
            } else {
                if (searchEmpty) searchEmpty.style.display = 'block';
            }
            break;

        case 'error':
            if (searchError) searchError.style.display = 'block';
            break;

        default:
            break;
    }
}

function renderSearchResults() {
    const container = document.getElementById('search-results-list');
    if (!container) return;

    container.innerHTML = SearchState.results.map(doc => `
        <div class="search-result-item" data-document-id="${doc.document_id}">
            <div class="result-header">
                <input type="checkbox"
                       class="document-checkbox"
                       data-document-id="${doc.document_id}"
                       ${SearchState.selectedDocuments.has(doc.document_id) ? 'checked' : ''}
                       onchange="toggleDocumentSelection('${doc.document_id}')">
                <div class="result-title">
                    <h4>${escapeHtml(doc.filename || 'Unbenannt')}</h4>
                    <span class="result-type">${escapeHtml(doc.document_type || 'Unbekannt')}</span>
                </div>
                <div class="result-score">
                    ${doc.score ? `<span class="score-badge">${(doc.score * 100).toFixed(1)}%</span>` : ''}
                </div>
            </div>

            ${doc.highlight ? `
                <div class="result-highlight">
                    ${sanitizeHighlight(doc.highlight)}
                </div>
            ` : ''}

            <div class="result-meta">
                <span class="meta-item">
                    <span class="meta-icon">&#128197;</span>
                    ${formatDate(doc.created_at)}
                </span>
                ${doc.ocr_confidence ? `
                    <span class="meta-item">
                        <span class="meta-icon">&#128200;</span>
                        Konfidenz: ${doc.ocr_confidence.toFixed(1)}%
                    </span>
                ` : ''}
                ${doc.has_embedding ? `
                    <span class="meta-item embedding-badge">
                        <span class="meta-icon">&#129302;</span>
                        Embedding
                    </span>
                ` : ''}
            </div>

            ${doc.tags && doc.tags.length > 0 ? `
                <div class="result-tags">
                    ${doc.tags.map(tag => `<span class="tag">${escapeHtml(tag)}</span>`).join('')}
                </div>
            ` : ''}

            <div class="result-actions">
                <button class="btn-small" onclick="viewDocument('${doc.document_id}')">
                    Anzeigen
                </button>
                <button class="btn-small btn-secondary" onclick="showSimilarDocuments('${doc.document_id}')">
                    Aehnliche
                </button>
            </div>
        </div>
    `).join('');

    // Render pagination
    renderPagination();
}

function renderPagination() {
    const container = document.getElementById('search-pagination');
    if (!container) return;

    const totalPages = Math.ceil(SearchState.totalResults / SearchState.perPage);

    if (totalPages <= 1) {
        container.innerHTML = '';
        return;
    }

    let paginationHTML = '<div class="pagination">';

    // Previous button
    paginationHTML += `
        <button class="pagination-btn"
                ${SearchState.currentPage === 1 ? 'disabled' : ''}
                onclick="goToPage(${SearchState.currentPage - 1})">
            &laquo; Zurueck
        </button>
    `;

    // Page numbers
    const maxVisiblePages = 5;
    let startPage = Math.max(1, SearchState.currentPage - Math.floor(maxVisiblePages / 2));
    let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);

    if (endPage - startPage < maxVisiblePages - 1) {
        startPage = Math.max(1, endPage - maxVisiblePages + 1);
    }

    for (let i = startPage; i <= endPage; i++) {
        paginationHTML += `
            <button class="pagination-btn ${i === SearchState.currentPage ? 'active' : ''}"
                    onclick="goToPage(${i})">
                ${i}
            </button>
        `;
    }

    // Next button
    paginationHTML += `
        <button class="pagination-btn"
                ${SearchState.currentPage === totalPages ? 'disabled' : ''}
                onclick="goToPage(${SearchState.currentPage + 1})">
            Weiter &raquo;
        </button>
    `;

    paginationHTML += '</div>';
    container.innerHTML = paginationHTML;
}

function goToPage(page) {
    if (page < 1) return;
    const totalPages = Math.ceil(SearchState.totalResults / SearchState.perPage);
    if (page > totalPages) return;

    SearchState.currentPage = page;
    performSearch();

    // Scroll to top of results
    const resultsContainer = document.getElementById('search-results');
    if (resultsContainer) {
        resultsContainer.scrollIntoView({ behavior: 'smooth' });
    }
}

// ==================== Analytics Tracking ====================

/**
 * Track a click on a search result
 */
async function trackSearchClick(documentId, isDownload = false) {
    if (!SearchState.analyticsId) return;

    // Find position of clicked document in results
    const position = SearchState.results.findIndex(doc => doc.document_id === documentId || doc.id === documentId) + 1;
    if (position === 0) return;

    try {
        const params = new URLSearchParams({
            analytics_id: SearchState.analyticsId,
            position: position,
            is_download: isDownload
        });

        await api.post(`/documents/stats/search-analytics/click?${params.toString()}`);
    } catch (error) {
        // Silent fail - don't disrupt user experience for analytics
        console.debug('Analytics click tracking failed:', error);
    }
}

// ==================== Document View ====================

async function viewDocument(documentId) {
    // Track the click for analytics
    trackSearchClick(documentId, false);

    const document = await getDocumentDetails(documentId);
    if (!document) return;

    // Show document detail modal/panel
    const modal = document.getElementById('document-detail-modal');
    if (modal) {
        modal.style.display = 'flex';
        renderDocumentDetail(document);
    }
}

function renderDocumentDetail(doc) {
    const container = document.getElementById('document-detail-content');
    if (!container) return;

    container.innerHTML = `
        <div class="document-detail">
            <div class="detail-header">
                <h3>${escapeHtml(doc.filename || 'Unbenannt')}</h3>
                <button class="close-btn" onclick="closeDocumentDetail()">&times;</button>
            </div>

            <div class="detail-meta">
                <div class="meta-row">
                    <span class="meta-label">Dokumenttyp:</span>
                    <span class="meta-value">${escapeHtml(doc.document_type || 'Unbekannt')}</span>
                </div>
                <div class="meta-row">
                    <span class="meta-label">Status:</span>
                    <span class="meta-value status-${doc.status}">${escapeHtml(doc.status || 'Unbekannt')}</span>
                </div>
                <div class="meta-row">
                    <span class="meta-label">Erstellt:</span>
                    <span class="meta-value">${formatDate(doc.created_at)}</span>
                </div>
                <div class="meta-row">
                    <span class="meta-label">Sprache:</span>
                    <span class="meta-value">${escapeHtml(doc.language || 'de')}</span>
                </div>
                ${doc.ocr_confidence ? `
                    <div class="meta-row">
                        <span class="meta-label">OCR-Konfidenz:</span>
                        <span class="meta-value">${doc.ocr_confidence.toFixed(1)}%</span>
                    </div>
                ` : ''}
            </div>

            ${doc.tags && doc.tags.length > 0 ? `
                <div class="detail-tags">
                    <span class="meta-label">Tags:</span>
                    <div class="tags-list">
                        ${doc.tags.map(tag => `<span class="tag">${escapeHtml(tag)}</span>`).join('')}
                    </div>
                </div>
            ` : ''}

            <div class="detail-text">
                <h4>Extrahierter Text</h4>
                <div class="text-content">
                    ${escapeHtml(doc.extracted_text || 'Kein Text verfuegbar')}
                </div>
            </div>

            <div class="detail-actions">
                <button class="btn" onclick="copyDocumentText('${doc.id}')">
                    Text kopieren
                </button>
                <button class="btn btn-secondary" onclick="showSimilarDocuments('${doc.id}')">
                    Aehnliche Dokumente
                </button>
            </div>
        </div>
    `;
}

function closeDocumentDetail() {
    const modal = document.getElementById('document-detail-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

async function showSimilarDocuments(documentId) {
    const similar = await findSimilarDocuments(documentId);
    if (similar.length === 0) {
        showToast('Keine aehnlichen Dokumente gefunden', 'info');
        return;
    }

    // Show similar documents panel
    const panel = document.getElementById('similar-documents-panel');
    if (panel) {
        panel.style.display = 'block';
        renderSimilarDocuments(similar);
    }
}

function renderSimilarDocuments(documents) {
    const container = document.getElementById('similar-documents-list');
    if (!container) return;

    container.innerHTML = documents.map(doc => `
        <div class="similar-document-item" onclick="viewDocument('${doc.document_id}')">
            <div class="similar-title">${escapeHtml(doc.filename || 'Unbenannt')}</div>
            <div class="similar-score">
                <span class="similarity-badge">${(doc.similarity * 100).toFixed(1)}% aehnlich</span>
            </div>
            <div class="similar-type">${escapeHtml(doc.document_type || 'Unbekannt')}</div>
        </div>
    `).join('');
}

function closeSimilarPanel() {
    const panel = document.getElementById('similar-documents-panel');
    if (panel) {
        panel.style.display = 'none';
    }
}

// ==================== Search History ====================

function addToSearchHistory(query, searchType, resultCount) {
    SearchState.searchHistory.unshift({
        query,
        searchType,
        resultCount,
        timestamp: new Date().toISOString()
    });

    // Keep only last 20 searches
    if (SearchState.searchHistory.length > 20) {
        SearchState.searchHistory.pop();
    }

    // Save to localStorage
    try {
        localStorage.setItem('searchHistory', JSON.stringify(SearchState.searchHistory));
    } catch (e) {
        console.warn('Suchverlauf konnte nicht gespeichert werden:', e);
    }
}

function loadSearchHistory() {
    try {
        const saved = localStorage.getItem('searchHistory');
        if (saved) {
            SearchState.searchHistory = JSON.parse(saved);
        }
    } catch (e) {
        console.warn('Suchverlauf konnte nicht geladen werden:', e);
    }
}

function showSearchHistory() {
    const container = document.getElementById('search-history');
    if (!container) return;

    container.innerHTML = SearchState.searchHistory.map(item => `
        <div class="history-item" onclick="repeatSearch('${escapeHtml(item.query)}', '${item.searchType}')">
            <span class="history-query">${escapeHtml(item.query)}</span>
            <span class="history-meta">
                ${item.searchType} - ${item.resultCount} Ergebnisse
            </span>
        </div>
    `).join('');
}

function repeatSearch(query, searchType) {
    const searchInput = document.getElementById('search-input');
    const searchTypeSelect = document.getElementById('search-type');

    if (searchInput) searchInput.value = query;
    if (searchTypeSelect) searchTypeSelect.value = searchType;

    SearchState.query = query;
    SearchState.searchType = searchType;
    performSearch();
}

// ==================== Utility Functions ====================

function formatDate(dateString) {
    if (!dateString) return 'Unbekannt';
    try {
        return new Date(dateString).toLocaleDateString('de-DE', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch {
        return dateString;
    }
}

function copyDocumentText(documentId) {
    const doc = SearchState.results.find(d => d.id === documentId);
    if (doc && doc.extracted_text) {
        navigator.clipboard.writeText(doc.extracted_text)
            .then(() => showToast('Text kopiert', 'success'))
            .catch(() => showToast('Kopieren fehlgeschlagen', 'error'));
    }
}

// ==================== Document Statistics ====================

async function loadDocumentStatistics() {
    if (!authManager.isAuthenticated()) return;

    try {
        const stats = await api.get('/documents/stats/summary');
        updateStatisticsUI(stats);
    } catch (error) {
        console.error('Statistik-Fehler:', error);
    }
}

function updateStatisticsUI(stats) {
    const container = document.getElementById('document-statistics');
    if (!container) return;

    container.innerHTML = `
        <div class="stat-card">
            <div class="stat-value">${stats.total_documents || 0}</div>
            <div class="stat-label">Dokumente gesamt</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">${stats.documents_with_embeddings || 0}</div>
            <div class="stat-label">Mit Embedding</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">${stats.embedding_coverage_percent?.toFixed(1) || 0}%</div>
            <div class="stat-label">Embedding-Abdeckung</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">${stats.average_ocr_confidence?.toFixed(1) || 0}%</div>
            <div class="stat-label">OCR-Konfidenz</div>
        </div>
    `;
}

// ==================== Exports ====================

window.SearchState = SearchState;
window.initializeSearch = initializeSearch;
window.performSearch = performSearch;
window.findSimilarDocuments = findSimilarDocuments;
window.listDocuments = listDocuments;
window.viewDocument = viewDocument;
window.toggleDocumentSelection = toggleDocumentSelection;
window.goToPage = goToPage;
window.clearFilters = clearFilters;
window.showBatchDeleteConfirm = showBatchDeleteConfirm;
window.showBatchTagDialog = showBatchTagDialog;
window.hideBatchTagDialog = hideBatchTagDialog;
window.submitBatchTag = submitBatchTag;
window.showBatchExportDialog = showBatchExportDialog;
window.hideBatchExportDialog = hideBatchExportDialog;
window.submitBatchExport = submitBatchExport;
window.closeDocumentDetail = closeDocumentDetail;
window.showSimilarDocuments = showSimilarDocuments;
window.closeSimilarPanel = closeSimilarPanel;
window.copyDocumentText = copyDocumentText;
window.loadDocumentStatistics = loadDocumentStatistics;
window.repeatSearch = repeatSearch;
window.trackSearchClick = trackSearchClick;
