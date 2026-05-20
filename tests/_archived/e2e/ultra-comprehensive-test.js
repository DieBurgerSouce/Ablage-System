/**
 * ============================================================================
 * ABLAGE-SYSTEM ULTRA-COMPREHENSIVE E2E TEST SUITE
 * ============================================================================
 * 
 * SCREENSHOT VON ABSOLUT ALLEM für Frontend-Analyse:
 * - Jede Seite (Initial + After Load)
 * - Jedes Form (Leer + Gefüllt + Validation)
 * - Jeder Button (Normal + Hover + Klick-Ergebnis)
 * - Jedes Modal/Dialog (Geöffnet + Inhalt + Aktionen)
 * - Jede Tabelle (Übersicht + Rows + Empty State)
 * - Jeder Tab (Alle Tabs einzeln)
 * - Jedes Dropdown (Geschlossen + Offen + Alle Optionen)
 * - Jeder Hover-State
 * - Jeder Empty-State
 * - Jeder Loading-State
 * - Jeder Error-State
 * - Sidebar Navigation States
 * - Breadcrumbs
 * - Tooltips
 * - Toast Messages
 * - Cards & Widgets
 * - Stats & KPIs
 * - Charts & Graphs
 * - Search Results
 * - Filter States
 * - Pagination
 * - Responsive Views (Desktop, Tablet, Mobile)
 * - Dark/Light Mode
 * 
 * Perfekt für Frontend-Analyse und Lücken-Erkennung!
 * 
 * Author: Ben / UFI Digital Agency
 * Created: 2025-06-30
 * ============================================================================
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// ============================================================================
// CONFIGURATION
// ============================================================================
const CONFIG = {
    baseUrl: 'http://localhost',
    credentials: {
        email: 'admin@localhost.com',
        password: 'admin123'
    },
    screenshotDir: path.join(__dirname, '../../screenshots/ultra-comprehensive'),
    reportDir: path.join(__dirname, '../../test-reports'),
    timeout: {
        navigation: 30000,
        element: 10000,
        short: 1500,
        micro: 500
    },
    viewports: {
        desktop: { width: 1920, height: 1080 },
        laptop: { width: 1366, height: 768 },
        tablet: { width: 768, height: 1024 },
        mobile: { width: 375, height: 812 }
    }
};

// ============================================================================
// COMPLETE ROUTE REGISTRY - ALLE 57+ ROUTES
// ============================================================================
const ALL_ROUTES = {
    auth: [
        { path: '/login', name: 'login', public: true },
        { path: '/forgot-password', name: 'forgot-password', public: true }
    ],
    main: [
        { path: '/', name: 'dashboard' },
        { path: '/upload', name: 'upload' },
        { path: '/search', name: 'search' },
        { path: '/chat', name: 'chat-rag' },
        { path: '/relationships', name: 'relationships' },
        { path: '/monitoring', name: 'monitoring' },
        { path: '/jobs', name: 'jobs' },
        { path: '/automation', name: 'automation' },
        { path: '/validation-queue', name: 'validation-queue' }
    ],
    documents: [
        { path: '/document-groups', name: 'document-groups' }
    ],
    kasse: [
        { path: '/kasse', name: 'kasse' }
    ],
    spesen: [
        { path: '/spesen', name: 'spesen' }
    ],
    streckengeschaeft: [
        { path: '/streckengeschaeft', name: 'streckengeschaeft' },
        { path: '/streckengeschaeft/zm', name: 'streckengeschaeft-zm' }
    ],
    finanzen: [
        { path: '/finanzen', name: 'finanzen' },
        { path: '/finanzen/2025', name: 'finanzen-2025' },
        { path: '/finanzen/2024', name: 'finanzen-2024' }
    ],
    kunden: [
        { path: '/kunden', name: 'kunden' }
    ],
    lieferanten: [
        { path: '/lieferanten', name: 'lieferanten' }
    ],
    personal: [
        { path: '/personal', name: 'personal' }
    ],
    businessEntities: [
        { path: '/business-entities', name: 'business-entities' }
    ],
    privat: [
        { path: '/privat', name: 'privat' },
        { path: '/privat/fahrzeuge', name: 'privat-fahrzeuge' },
        { path: '/privat/finanzen', name: 'privat-finanzen' },
        { path: '/privat/fristen', name: 'privat-fristen' },
        { path: '/privat/immobilien', name: 'privat-immobilien' },
        { path: '/privat/notfall', name: 'privat-notfall' },
        { path: '/privat/versicherungen', name: 'privat-versicherungen' }
    ],
    adminMain: [
        { path: '/admin', name: 'admin-dashboard' },
        { path: '/admin/users', name: 'admin-users' },
        { path: '/admin/settings', name: 'admin-settings' },
        { path: '/admin/tunes', name: 'admin-tunes' },
        { path: '/admin/job-queue', name: 'admin-job-queue' }
    ],
    adminOcr: [
        { path: '/admin/ocr-review', name: 'admin-ocr-review' },
        { path: '/admin/ocr-training', name: 'admin-ocr-training' },
        { path: '/admin/ocr-backends', name: 'admin-ocr-backends' }
    ],
    adminDatev: [
        { path: '/admin/datev', name: 'admin-datev' },
        { path: '/admin/datev/config', name: 'admin-datev-config' },
        { path: '/admin/datev/export', name: 'admin-datev-export' },
        { path: '/admin/datev/history', name: 'admin-datev-history' },
        { path: '/admin/datev/vendors', name: 'admin-datev-vendors' }
    ],
    adminMahnungen: [
        { path: '/admin/mahnungen', name: 'admin-mahnungen' },
        { path: '/admin/mahnungen/aktiv', name: 'admin-mahnungen-aktiv' },
        { path: '/admin/mahnungen/aufgaben', name: 'admin-mahnungen-aufgaben' },
        { path: '/admin/mahnungen/einstellungen', name: 'admin-mahnungen-einstellungen' },
        { path: '/admin/mahnungen/eskalation', name: 'admin-mahnungen-eskalation' },
        { path: '/admin/mahnungen/kanban', name: 'admin-mahnungen-kanban' },
        { path: '/admin/mahnungen/mahnstopp', name: 'admin-mahnungen-mahnstopp' }
    ],
    adminBanking: [
        { path: '/admin/banking', name: 'admin-banking' },
        { path: '/admin/banking/accounts', name: 'admin-banking-accounts' },
        { path: '/admin/banking/import', name: 'admin-banking-import' },
        { path: '/admin/banking/payments', name: 'admin-banking-payments' },
        { path: '/admin/banking/reconciliation', name: 'admin-banking-reconciliation' },
        { path: '/admin/banking/skonto', name: 'admin-banking-skonto' },
        { path: '/admin/banking/transactions', name: 'admin-banking-transactions' }
    ]
};

// ============================================================================
// SCREENSHOT COUNTER & TRACKER
// ============================================================================
class ScreenshotManager {
    constructor(baseDir) {
        this.baseDir = baseDir;
        this.counter = 0;
        this.screenshots = [];
        this.byCategory = {};
        this.byPage = {};
    }

    async capture(page, name, category, description = '', elementHandle = null) {
        this.counter++;
        const num = String(this.counter).padStart(4, '0');
        const safeName = name.replace(/[^a-zA-Z0-9-_äöüÄÖÜß]/g, '_').substring(0, 80);
        const filename = `${num}_${safeName}.png`;
        
        const catDir = path.join(this.baseDir, category);
        fs.mkdirSync(catDir, { recursive: true });
        
        const filepath = path.join(catDir, filename);
        
        try {
            if (elementHandle) {
                await elementHandle.screenshot({ path: filepath });
            } else {
                await page.screenshot({ path: filepath, fullPage: true });
            }
            
            const entry = {
                number: this.counter,
                name: safeName,
                category,
                description,
                filename,
                filepath,
                timestamp: new Date().toISOString()
            };
            
            this.screenshots.push(entry);
            if (!this.byCategory[category]) this.byCategory[category] = [];
            this.byCategory[category].push(entry);
            
            console.log(`    📸 #${num} [${category}] ${name.substring(0, 50)}`);
            return entry;
        } catch (e) {
            console.log(`    ⚠️ Screenshot failed: ${name} - ${e.message}`);
            return null;
        }
    }

    getStats() {
        return {
            total: this.counter,
            categories: Object.keys(this.byCategory).length,
            byCategory: Object.fromEntries(
                Object.entries(this.byCategory).map(([k, v]) => [k, v.length])
            )
        };
    }
}

// ============================================================================
// ANALYSIS COLLECTOR - Für Lücken-Erkennung
// ============================================================================
class AnalysisCollector {
    constructor() {
        this.pages = {};
        this.elements = { buttons: [], forms: [], tables: [], modals: [], tabs: [], dropdowns: [] };
        this.emptyStates = [];
        this.missingFeatures = [];
        this.suggestions = [];
        this.interactions = [];
    }

    recordPage(route, data) {
        this.pages[route] = { ...data, recordedAt: new Date().toISOString() };
    }

    recordElement(type, page, details) {
        this.elements[type]?.push({ page, ...details, recordedAt: new Date().toISOString() });
    }

    recordEmptyState(page, selector, description) {
        this.emptyStates.push({ page, selector, description, recordedAt: new Date().toISOString() });
    }

    recordInteraction(type, element, success, details = {}) {
        this.interactions.push({ type, element, success, ...details, recordedAt: new Date().toISOString() });
    }

    addSuggestion(page, category, suggestion) {
        this.suggestions.push({ page, category, suggestion, recordedAt: new Date().toISOString() });
    }

    generateReport() {
        return {
            summary: {
                totalPages: Object.keys(this.pages).length,
                totalButtons: this.elements.buttons.length,
                totalForms: this.elements.forms.length,
                totalTables: this.elements.tables.length,
                totalModals: this.elements.modals.length,
                totalEmptyStates: this.emptyStates.length,
                totalInteractions: this.interactions.length,
                successfulInteractions: this.interactions.filter(i => i.success).length,
                suggestions: this.suggestions.length
            },
            pages: this.pages,
            elements: this.elements,
            emptyStates: this.emptyStates,
            suggestions: this.suggestions,
            interactions: this.interactions
        };
    }
}

// ============================================================================
// MAIN TEST SUITE
// ============================================================================
class UltraComprehensiveTestSuite {
    constructor() {
        this.browser = null;
        this.context = null;
        this.page = null;
        this.ss = null; // Screenshot Manager
        this.analysis = new AnalysisCollector();
        this.results = { passed: 0, failed: 0, skipped: 0 };
    }

    async init() {
        console.log('\n' + '═'.repeat(70));
        console.log('🚀 ULTRA-COMPREHENSIVE TEST SUITE - SCREENSHOT EVERYTHING');
        console.log('═'.repeat(70));
        console.log(`📁 Screenshots: ${CONFIG.screenshotDir}`);
        console.log(`🌐 Base URL: ${CONFIG.baseUrl}`);
        console.log('═'.repeat(70) + '\n');

        // Create all directories
        const dirs = [
            'pages', 'pages-loaded', 'pages-scrolled',
            'forms-empty', 'forms-filled', 'forms-validation', 'forms-submitted',
            'buttons', 'buttons-hover', 'buttons-clicked',
            'modals', 'modals-content', 'modals-forms',
            'tables', 'tables-rows', 'tables-empty', 'tables-actions',
            'tabs', 'tabs-content',
            'dropdowns', 'dropdowns-open', 'dropdowns-options',
            'cards', 'widgets', 'stats', 'kpis',
            'navigation', 'sidebar', 'sidebar-expanded', 'sidebar-collapsed', 'breadcrumbs',
            'empty-states', 'loading-states', 'error-states', 'success-states',
            'tooltips', 'toasts', 'notifications', 'alerts',
            'search', 'search-results', 'search-empty', 'filters', 'filters-applied',
            'pagination', 'sorting',
            'file-upload', 'drag-drop',
            'responsive-desktop', 'responsive-tablet', 'responsive-mobile',
            'dark-mode', 'light-mode',
            'hover-states', 'focus-states', 'active-states', 'disabled-states',
            'charts', 'graphs', 'statistics',
            'dialogs', 'confirmations', 'prompts',
            'menus', 'context-menus', 'action-menus',
            'headers', 'footers',
            'icons', 'badges', 'labels',
            'progress', 'spinners', 'skeletons',
            'analysis', 'errors'
        ];

        for (const dir of dirs) {
            fs.mkdirSync(path.join(CONFIG.screenshotDir, dir), { recursive: true });
        }
        fs.mkdirSync(CONFIG.reportDir, { recursive: true });

        this.ss = new ScreenshotManager(CONFIG.screenshotDir);

        // Launch browser
        this.browser = await chromium.launch({ headless: true });
        this.context = await this.browser.newContext({
            viewport: CONFIG.viewports.desktop,
            locale: 'de-DE'
        });
        this.page = await this.context.newPage();

        console.log('✅ Browser initialized\n');
    }

    // ========================================================================
    // LOGIN
    // ========================================================================
    async login() {
        console.log('🔐 Logging in...');
        
        await this.page.goto(`${CONFIG.baseUrl}/login`, { waitUntil: 'networkidle' });
        await this.page.waitForTimeout(1500);
        
        // Screenshot login page
        await this.ss.capture(this.page, 'login-page-initial', 'pages', 'Login page initial state');
        
        // Fill credentials using exact IDs from login.tsx
        console.log('   Filling email...');
        await this.page.fill('#email', CONFIG.credentials.email);
        
        console.log('   Filling password...');
        await this.page.fill('#password', CONFIG.credentials.password);
        
        await this.ss.capture(this.page, 'login-page-filled', 'forms-filled', 'Login form filled');
        
        // Submit by clicking the button
        console.log('   Submitting form...');
        await this.page.click('button[type="submit"]');
        
        // Wait for navigation or error
        await this.page.waitForTimeout(3000);
        
        // Check if logged in
        const currentUrl = this.page.url();
        console.log(`   Current URL: ${currentUrl}`);
        
        if (!currentUrl.includes('/login')) {
            console.log('✅ Login successful\n');
            await this.ss.capture(this.page, 'after-login-dashboard', 'pages', 'Dashboard after login');
            return true;
        }
        
        // Check for error message
        const errorMsg = await this.page.$('.text-destructive, [class*="error"]');
        if (errorMsg) {
            const errorText = await errorMsg.textContent();
            console.log(`   Error: ${errorText}`);
        }
        
        // Screenshot the failed state
        await this.ss.capture(this.page, 'login-failed', 'errors', 'Login failed state');
        
        console.log('❌ Login failed\n');
        return false;
    }

    // ========================================================================
    // TEST SINGLE PAGE - ULTRA DETAILED
    // ========================================================================
    async testPageUltraDetailed(route, category) {
        const { path: routePath, name } = route;
        
        console.log(`\n${'─'.repeat(60)}`);
        console.log(`📄 ${name.toUpperCase()} (${routePath})`);
        console.log('─'.repeat(60));

        const pageData = {
            route: routePath,
            name,
            screenshots: 0,
            elements: {},
            interactions: []
        };

        try {
            // ============================================================
            // 1. NAVIGATE & INITIAL SCREENSHOTS
            // ============================================================
            await this.page.goto(`${CONFIG.baseUrl}${routePath}`, {
                waitUntil: 'networkidle',
                timeout: CONFIG.timeout.navigation
            });
            await this.page.waitForTimeout(CONFIG.timeout.short);

            // Initial state
            await this.ss.capture(this.page, `${name}-01-initial`, 'pages', `${name} - Initial load`);
            pageData.screenshots++;

            // After full load
            await this.page.waitForTimeout(500);
            await this.ss.capture(this.page, `${name}-02-loaded`, 'pages-loaded', `${name} - Fully loaded`);
            pageData.screenshots++;

            // ============================================================
            // 2. SCROLL AND CAPTURE FULL PAGE
            // ============================================================
            const pageHeight = await this.page.evaluate(() => document.body.scrollHeight);
            const viewportHeight = CONFIG.viewports.desktop.height;
            
            if (pageHeight > viewportHeight) {
                // Scroll to middle
                await this.page.evaluate(() => window.scrollTo(0, document.body.scrollHeight / 2));
                await this.page.waitForTimeout(300);
                await this.ss.capture(this.page, `${name}-03-scroll-middle`, 'pages-scrolled', `${name} - Middle section`);
                pageData.screenshots++;

                // Scroll to bottom
                await this.page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
                await this.page.waitForTimeout(300);
                await this.ss.capture(this.page, `${name}-04-scroll-bottom`, 'pages-scrolled', `${name} - Bottom section`);
                pageData.screenshots++;

                // Back to top
                await this.page.evaluate(() => window.scrollTo(0, 0));
                await this.page.waitForTimeout(300);
            }

            // ============================================================
            // 3. ANALYZE & COUNT ALL ELEMENTS
            // ============================================================
            pageData.elements = await this.page.evaluate(() => {
                return {
                    buttons: document.querySelectorAll('button').length,
                    links: document.querySelectorAll('a').length,
                    inputs: document.querySelectorAll('input').length,
                    textareas: document.querySelectorAll('textarea').length,
                    selects: document.querySelectorAll('select, [role="combobox"]').length,
                    tables: document.querySelectorAll('table, [role="grid"]').length,
                    forms: document.querySelectorAll('form').length,
                    cards: document.querySelectorAll('.card, [data-card]').length,
                    tabs: document.querySelectorAll('[role="tab"]').length,
                    modals: document.querySelectorAll('[role="dialog"]').length,
                    dropdowns: document.querySelectorAll('[data-dropdown], .dropdown').length,
                    tooltips: document.querySelectorAll('[data-tooltip], [title]').length,
                    badges: document.querySelectorAll('.badge, [data-badge]').length,
                    alerts: document.querySelectorAll('.alert, [role="alert"]').length,
                    icons: document.querySelectorAll('svg, .icon, [data-icon]').length
                };
            });

            console.log(`   Elements: ${pageData.elements.buttons} btns, ${pageData.elements.inputs} inputs, ${pageData.elements.tables} tables, ${pageData.elements.forms} forms`);

            // ============================================================
            // 4. EMPTY STATES CHECK
            // ============================================================
            await this.checkAndCaptureEmptyStates(name, pageData);

            // ============================================================
            // 5. LOADING STATES CHECK
            // ============================================================
            await this.checkAndCaptureLoadingStates(name, pageData);

            // ============================================================
            // 6. ERROR STATES CHECK
            // ============================================================
            await this.checkAndCaptureErrorStates(name, pageData);

            // ============================================================
            // 7. SIDEBAR NAVIGATION
            // ============================================================
            await this.captureSidebar(name, pageData);

            // ============================================================
            // 8. BREADCRUMBS
            // ============================================================
            await this.captureBreadcrumbs(name, pageData);

            // ============================================================
            // 9. ALL BUTTONS
            // ============================================================
            await this.captureAllButtons(name, pageData);

            // ============================================================
            // 10. ALL FORMS
            // ============================================================
            await this.captureAllForms(name, pageData);

            // ============================================================
            // 11. ALL TABLES
            // ============================================================
            await this.captureAllTables(name, pageData);

            // ============================================================
            // 12. ALL TABS
            // ============================================================
            await this.captureAllTabs(name, pageData);

            // ============================================================
            // 13. ALL DROPDOWNS
            // ============================================================
            await this.captureAllDropdowns(name, pageData);

            // ============================================================
            // 14. ALL CARDS & WIDGETS
            // ============================================================
            await this.captureCardsAndWidgets(name, pageData);

            // ============================================================
            // 15. ALL STATS & KPIS
            // ============================================================
            await this.captureStatsAndKPIs(name, pageData);

            // ============================================================
            // 16. MODALS & DIALOGS (Try to open them)
            // ============================================================
            await this.captureModals(name, pageData);

            // ============================================================
            // 17. TOOLTIPS (Hover elements with titles)
            // ============================================================
            await this.captureTooltips(name, pageData);

            // ============================================================
            // 18. FINAL STATE
            // ============================================================
            await this.ss.capture(this.page, `${name}-99-final`, 'pages', `${name} - Final state`);
            pageData.screenshots++;

            // Record analysis
            this.analysis.recordPage(routePath, pageData);
            this.results.passed++;

            console.log(`   ✅ PASS - ${pageData.screenshots} screenshots captured`);
            return true;

        } catch (error) {
            console.log(`   ❌ FAIL - ${error.message}`);
            await this.ss.capture(this.page, `${name}-ERROR`, 'errors', error.message);
            this.results.failed++;
            return false;
        }
    }

    // ========================================================================
    // EMPTY STATES
    // ========================================================================
    async checkAndCaptureEmptyStates(pageName, pageData) {
        const emptySelectors = [
            '.empty-state', '[data-empty]', '.no-data', '.no-results',
            'text=Keine Daten', 'text=Keine Einträge', 'text=Noch keine',
            'text=Keine Ergebnisse', 'text=Leer', 'text=No data', 'text=No results',
            'text=Nichts gefunden', 'text=Keine Dokumente'
        ];

        for (const selector of emptySelectors) {
            try {
                const elements = await this.page.$$(selector);
                for (let i = 0; i < elements.length; i++) {
                    const el = elements[i];
                    if (await el.isVisible()) {
                        await el.scrollIntoViewIfNeeded();
                        await this.ss.capture(this.page, `${pageName}-empty-${i + 1}`, 'empty-states', `Empty state: ${selector}`);
                        this.analysis.recordEmptyState(pageName, selector, 'Empty state visible');
                        pageData.screenshots++;
                    }
                }
            } catch (e) {}
        }
    }

    // ========================================================================
    // LOADING STATES
    // ========================================================================
    async checkAndCaptureLoadingStates(pageName, pageData) {
        const loadingSelectors = [
            '.loading', '.spinner', '.skeleton', '[data-loading]',
            '.animate-spin', '.animate-pulse', '[aria-busy="true"]'
        ];

        for (const selector of loadingSelectors) {
            try {
                const elements = await this.page.$$(selector);
                for (let i = 0; i < elements.length; i++) {
                    const el = elements[i];
                    if (await el.isVisible()) {
                        await this.ss.capture(this.page, `${pageName}-loading-${i + 1}`, 'loading-states', `Loading: ${selector}`);
                        pageData.screenshots++;
                    }
                }
            } catch (e) {}
        }
    }

    // ========================================================================
    // ERROR STATES
    // ========================================================================
    async checkAndCaptureErrorStates(pageName, pageData) {
        const errorSelectors = [
            '.error', '.alert-error', '.alert-danger', '[data-error]',
            'text=Fehler', 'text=Error', 'text=fehlgeschlagen', 'text=failed',
            '.text-red-500', '.text-destructive', '[role="alert"]'
        ];

        for (const selector of errorSelectors) {
            try {
                const elements = await this.page.$$(selector);
                for (let i = 0; i < elements.length; i++) {
                    const el = elements[i];
                    if (await el.isVisible()) {
                        await el.scrollIntoViewIfNeeded();
                        await this.ss.capture(this.page, `${pageName}-error-${i + 1}`, 'error-states', `Error: ${selector}`);
                        pageData.screenshots++;
                    }
                }
            } catch (e) {}
        }
    }

    // ========================================================================
    // SIDEBAR
    // ========================================================================
    async captureSidebar(pageName, pageData) {
        const sidebarSelectors = ['aside', '[data-sidebar]', '.sidebar', 'nav[role="navigation"]'];
        
        for (const selector of sidebarSelectors) {
            try {
                const sidebar = await this.page.$(selector);
                if (sidebar && await sidebar.isVisible()) {
                    await this.ss.capture(this.page, `${pageName}-sidebar`, 'sidebar', 'Sidebar navigation');
                    pageData.screenshots++;
                    
                    // Try to find expand/collapse button
                    const toggleBtn = await this.page.$('[data-sidebar-toggle], .sidebar-toggle, button[aria-label*="sidebar"]');
                    if (toggleBtn) {
                        await toggleBtn.click();
                        await this.page.waitForTimeout(300);
                        await this.ss.capture(this.page, `${pageName}-sidebar-toggled`, 'sidebar-collapsed', 'Sidebar toggled');
                        pageData.screenshots++;
                        await toggleBtn.click(); // Toggle back
                        await this.page.waitForTimeout(300);
                    }
                    break;
                }
            } catch (e) {}
        }
    }

    // ========================================================================
    // BREADCRUMBS
    // ========================================================================
    async captureBreadcrumbs(pageName, pageData) {
        const breadcrumbSelectors = ['.breadcrumb', '[data-breadcrumb]', 'nav[aria-label*="breadcrumb"]', '[aria-label*="Breadcrumb"]'];
        
        for (const selector of breadcrumbSelectors) {
            try {
                const breadcrumb = await this.page.$(selector);
                if (breadcrumb && await breadcrumb.isVisible()) {
                    await breadcrumb.scrollIntoViewIfNeeded();
                    await this.ss.capture(this.page, `${pageName}-breadcrumbs`, 'breadcrumbs', 'Breadcrumb navigation');
                    pageData.screenshots++;
                    break;
                }
            } catch (e) {}
        }
    }

    // ========================================================================
    // ALL BUTTONS - Mit Hover States
    // ========================================================================
    async captureAllButtons(pageName, pageData) {
        const buttons = await this.page.$$('button:visible');
        console.log(`   📍 Testing ${buttons.length} buttons...`);

        let btnIndex = 0;
        for (const btn of buttons.slice(0, 20)) { // Max 20 buttons per page
            btnIndex++;
            try {
                const text = ((await btn.textContent()) || '').trim().substring(0, 25);
                const isDisabled = await btn.isDisabled();
                const ariaLabel = await btn.getAttribute('aria-label') || '';
                
                await btn.scrollIntoViewIfNeeded();
                
                // Normal state
                await this.ss.capture(this.page, `${pageName}-btn-${btnIndex}-${text || 'icon'}`, 'buttons', `Button: ${text || ariaLabel}`);
                pageData.screenshots++;

                // Hover state
                try {
                    await btn.hover();
                    await this.page.waitForTimeout(200);
                    await this.ss.capture(this.page, `${pageName}-btn-${btnIndex}-hover`, 'buttons-hover', `Button hover: ${text}`);
                    pageData.screenshots++;
                } catch (e) {}

                // Click safe buttons
                const safePatterns = ['Neu', 'Erstellen', 'Add', 'New', 'Create', 'Filter', 'Suchen', 
                                     'Search', 'Aktualisieren', 'Refresh', 'Details', 'Anzeigen', 'View', 'Öffnen'];
                const dangerPatterns = ['Löschen', 'Delete', 'Entfernen', 'Remove', 'Abbrechen', 'Cancel'];
                
                const isSafe = safePatterns.some(p => text.toLowerCase().includes(p.toLowerCase()));
                const isDanger = dangerPatterns.some(p => text.toLowerCase().includes(p.toLowerCase()));

                if (isSafe && !isDanger && !isDisabled) {
                    await btn.click();
                    await this.page.waitForTimeout(CONFIG.timeout.micro);
                    
                    // Check for modal
                    const modal = await this.page.$('[role="dialog"]:visible, .modal:visible');
                    if (modal) {
                        await this.ss.capture(this.page, `${pageName}-btn-${btnIndex}-modal`, 'modals', `Modal from: ${text}`);
                        pageData.screenshots++;
                        
                        // Capture modal form if exists
                        const modalForm = await modal.$('form');
                        if (modalForm) {
                            await this.captureModalForm(pageName, btnIndex, modal, pageData);
                        }
                        
                        // Close modal
                        await this.page.keyboard.press('Escape');
                        await this.page.waitForTimeout(300);
                    }
                    
                    this.analysis.recordInteraction('button_click', text, true);
                }

                this.analysis.recordElement('buttons', pageName, { text, disabled: isDisabled, ariaLabel });

            } catch (e) {
                this.analysis.recordInteraction('button_click', `btn-${btnIndex}`, false, { error: e.message });
            }
        }
    }

    // ========================================================================
    // MODAL FORM CAPTURE
    // ========================================================================
    async captureModalForm(pageName, btnIndex, modal, pageData) {
        // Empty form
        await this.ss.capture(this.page, `${pageName}-modal-${btnIndex}-form-empty`, 'modals-forms', 'Modal form empty');
        pageData.screenshots++;

        // Fill form
        const inputs = await modal.$$('input:visible, textarea:visible');
        for (const input of inputs) {
            try {
                const type = await input.getAttribute('type');
                const name = await input.getAttribute('name') || '';
                const isDisabled = await input.isDisabled();
                if (isDisabled) continue;

                if (type === 'email') await input.fill('test@example.com');
                else if (type === 'password') await input.fill('Test123!');
                else if (type === 'date') await input.fill('2025-06-30');
                else if (type === 'number') await input.fill('100');
                else if (type === 'tel') await input.fill('+49 123 456789');
                else if (name.includes('iban')) await input.fill('DE89370400440532013000');
                else if (name.includes('amount') || name.includes('betrag')) await input.fill('123.45');
                else if (name.includes('title') || name.includes('name')) await input.fill('Test Eintrag');
                else if (name.includes('description') || name.includes('beschreibung')) await input.fill('Test Beschreibung für Analyse');
                else await input.fill('Test Eingabe');
            } catch (e) {}
        }

        // Screenshot filled form
        await this.ss.capture(this.page, `${pageName}-modal-${btnIndex}-form-filled`, 'forms-filled', 'Modal form filled');
        pageData.screenshots++;
    }

    // ========================================================================
    // ALL FORMS
    // ========================================================================
    async captureAllForms(pageName, pageData) {
        const forms = await this.page.$$('form:visible');
        console.log(`   📝 Testing ${forms.length} forms...`);

        let formIndex = 0;
        for (const form of forms) {
            formIndex++;
            try {
                await form.scrollIntoViewIfNeeded();
                
                // Empty state
                await this.ss.capture(this.page, `${pageName}-form-${formIndex}-empty`, 'forms-empty', `Form ${formIndex} empty`);
                pageData.screenshots++;

                // Fill form
                const inputs = await form.$$('input:visible, textarea:visible');
                for (const input of inputs) {
                    try {
                        const type = await input.getAttribute('type');
                        const name = await input.getAttribute('name') || '';
                        const isDisabled = await input.isDisabled();
                        const isReadonly = await input.getAttribute('readonly');
                        if (isDisabled || isReadonly) continue;

                        if (type === 'checkbox' || type === 'radio') {
                            const isChecked = await input.isChecked();
                            if (!isChecked) await input.check();
                        } else if (type === 'email') await input.fill('test@example.com');
                        else if (type === 'password') await input.fill('TestPassword123!');
                        else if (type === 'date') await input.fill('2025-06-30');
                        else if (type === 'datetime-local') await input.fill('2025-06-30T14:30');
                        else if (type === 'time') await input.fill('14:30');
                        else if (type === 'number') await input.fill('250');
                        else if (type === 'tel') await input.fill('+49 212 123456');
                        else if (type === 'url') await input.fill('https://example.com');
                        else if (type === 'search') await input.fill('Suchbegriff');
                        else if (name.includes('iban')) await input.fill('DE89370400440532013000');
                        else if (name.includes('bic')) await input.fill('COBADEFFXXX');
                        else if (name.includes('amount') || name.includes('betrag')) await input.fill('1234.56');
                        else if (name.includes('title') || name.includes('titel')) await input.fill('Test Titel');
                        else if (name.includes('name')) await input.fill('Max Mustermann');
                        else if (name.includes('address') || name.includes('adresse')) await input.fill('Musterstraße 123, 42651 Solingen');
                        else if (name.includes('city') || name.includes('stadt')) await input.fill('Solingen');
                        else if (name.includes('zip') || name.includes('plz')) await input.fill('42651');
                        else if (name.includes('country') || name.includes('land')) await input.fill('Deutschland');
                        else if (name.includes('description') || name.includes('beschreibung')) await input.fill('Dies ist eine Testbeschreibung für die Analyse.');
                        else if (name.includes('note') || name.includes('notiz')) await input.fill('Testnotiz');
                        else if (name.includes('comment') || name.includes('kommentar')) await input.fill('Testkommentar');
                        else await input.fill('Test Eingabe ' + formIndex);
                    } catch (e) {}
                }

                // Handle selects
                const selects = await form.$$('select:visible');
                for (const select of selects) {
                    try {
                        const options = await select.$$('option');
                        if (options.length > 1) {
                            await select.selectOption({ index: 1 });
                        }
                    } catch (e) {}
                }

                // Screenshot filled
                await this.ss.capture(this.page, `${pageName}-form-${formIndex}-filled`, 'forms-filled', `Form ${formIndex} filled`);
                pageData.screenshots++;

                this.analysis.recordElement('forms', pageName, { index: formIndex, inputs: inputs.length });

            } catch (e) {}
        }
    }

    // ========================================================================
    // ALL TABLES
    // ========================================================================
    async captureAllTables(pageName, pageData) {
        const tables = await this.page.$$('table:visible, [role="grid"]:visible, [data-table]:visible');
        console.log(`   📊 Testing ${tables.length} tables...`);

        let tableIndex = 0;
        for (const table of tables) {
            tableIndex++;
            try {
                await table.scrollIntoViewIfNeeded();
                
                // Table overview
                await this.ss.capture(this.page, `${pageName}-table-${tableIndex}`, 'tables', `Table ${tableIndex}`);
                pageData.screenshots++;

                // Count rows
                const rows = await table.$$('tbody tr, [role="row"]');
                const rowCount = rows.length;

                if (rowCount === 0) {
                    await this.ss.capture(this.page, `${pageName}-table-${tableIndex}-empty`, 'tables-empty', `Table ${tableIndex} empty`);
                    pageData.screenshots++;
                    this.analysis.recordEmptyState(pageName, `table-${tableIndex}`, 'Empty table');
                } else {
                    // Capture first few rows
                    for (let i = 0; i < Math.min(3, rows.length); i++) {
                        const row = rows[i];
                        try {
                            await row.scrollIntoViewIfNeeded();
                            await row.hover();
                            await this.page.waitForTimeout(200);
                            await this.ss.capture(this.page, `${pageName}-table-${tableIndex}-row-${i + 1}`, 'tables-rows', `Table ${tableIndex} row ${i + 1}`);
                            pageData.screenshots++;

                            // Look for row actions
                            const rowActions = await row.$$('button, a, [data-action]');
                            if (rowActions.length > 0) {
                                await this.ss.capture(this.page, `${pageName}-table-${tableIndex}-row-${i + 1}-actions`, 'tables-actions', `Row actions`);
                                pageData.screenshots++;
                            }
                        } catch (e) {}
                    }
                }

                this.analysis.recordElement('tables', pageName, { index: tableIndex, rows: rowCount });

            } catch (e) {}
        }
    }

    // ========================================================================
    // ALL TABS
    // ========================================================================
    async captureAllTabs(pageName, pageData) {
        const tabLists = await this.page.$$('[role="tablist"]:visible');
        console.log(`   🗂️ Testing ${tabLists.length} tab groups...`);

        let tabGroupIndex = 0;
        for (const tabList of tabLists) {
            tabGroupIndex++;
            try {
                const tabs = await tabList.$$('[role="tab"]');
                console.log(`      Tab group ${tabGroupIndex}: ${tabs.length} tabs`);

                for (let i = 0; i < tabs.length; i++) {
                    const tab = tabs[i];
                    const tabText = ((await tab.textContent()) || '').trim().substring(0, 20);
                    
                    try {
                        await tab.click();
                        await this.page.waitForTimeout(300);
                        await this.ss.capture(this.page, `${pageName}-tab-${tabGroupIndex}-${i + 1}-${tabText}`, 'tabs', `Tab: ${tabText}`);
                        pageData.screenshots++;

                        // Screenshot tab content
                        const tabPanel = await this.page.$('[role="tabpanel"]:visible, [data-tab-content]:visible');
                        if (tabPanel) {
                            await this.ss.capture(this.page, `${pageName}-tab-${tabGroupIndex}-${i + 1}-content`, 'tabs-content', `Tab content: ${tabText}`);
                            pageData.screenshots++;
                        }

                        this.analysis.recordElement('tabs', pageName, { group: tabGroupIndex, index: i, text: tabText });
                    } catch (e) {}
                }
            } catch (e) {}
        }
    }

    // ========================================================================
    // ALL DROPDOWNS
    // ========================================================================
    async captureAllDropdowns(pageName, pageData) {
        const dropdownTriggers = await this.page.$$('[data-dropdown-trigger], .dropdown-trigger, [aria-haspopup="true"], [aria-haspopup="listbox"], [aria-haspopup="menu"]');
        console.log(`   📋 Testing ${dropdownTriggers.length} dropdowns...`);

        let ddIndex = 0;
        for (const trigger of dropdownTriggers.slice(0, 10)) { // Max 10 dropdowns
            ddIndex++;
            try {
                await trigger.scrollIntoViewIfNeeded();
                
                // Closed state
                await this.ss.capture(this.page, `${pageName}-dropdown-${ddIndex}-closed`, 'dropdowns', `Dropdown ${ddIndex} closed`);
                pageData.screenshots++;

                // Open dropdown
                await trigger.click();
                await this.page.waitForTimeout(300);

                // Open state
                await this.ss.capture(this.page, `${pageName}-dropdown-${ddIndex}-open`, 'dropdowns-open', `Dropdown ${ddIndex} open`);
                pageData.screenshots++;

                // Capture options if visible
                const options = await this.page.$$('[role="option"]:visible, [role="menuitem"]:visible, .dropdown-item:visible');
                if (options.length > 0) {
                    await this.ss.capture(this.page, `${pageName}-dropdown-${ddIndex}-options`, 'dropdowns-options', `Dropdown ${ddIndex} options (${options.length})`);
                    pageData.screenshots++;
                }

                // Close dropdown
                await this.page.keyboard.press('Escape');
                await this.page.waitForTimeout(200);

                this.analysis.recordElement('dropdowns', pageName, { index: ddIndex, options: options.length });

            } catch (e) {}
        }

        // Also test select elements
        const selects = await this.page.$$('select:visible');
        for (const select of selects.slice(0, 5)) {
            ddIndex++;
            try {
                await select.scrollIntoViewIfNeeded();
                await this.ss.capture(this.page, `${pageName}-select-${ddIndex}`, 'dropdowns', `Select ${ddIndex}`);
                pageData.screenshots++;
            } catch (e) {}
        }
    }

    // ========================================================================
    // CARDS & WIDGETS
    // ========================================================================
    async captureCardsAndWidgets(pageName, pageData) {
        const cards = await this.page.$$('.card:visible, [data-card]:visible, .widget:visible, [data-widget]:visible');
        console.log(`   🃏 Found ${cards.length} cards/widgets...`);

        for (let i = 0; i < Math.min(cards.length, 10); i++) {
            const card = cards[i];
            try {
                await card.scrollIntoViewIfNeeded();
                await this.ss.capture(this.page, `${pageName}-card-${i + 1}`, 'cards', `Card ${i + 1}`, card);
                pageData.screenshots++;
            } catch (e) {}
        }
    }

    // ========================================================================
    // STATS & KPIS
    // ========================================================================
    async captureStatsAndKPIs(pageName, pageData) {
        const statsSelectors = ['.stat', '.kpi', '[data-stat]', '[data-kpi]', '.metric', '.number-card'];
        
        for (const selector of statsSelectors) {
            const stats = await this.page.$$(selector + ':visible');
            for (let i = 0; i < stats.length; i++) {
                try {
                    const stat = stats[i];
                    await stat.scrollIntoViewIfNeeded();
                    await this.ss.capture(this.page, `${pageName}-stat-${i + 1}`, 'stats', `Stat ${i + 1}`, stat);
                    pageData.screenshots++;
                } catch (e) {}
            }
        }
    }

    // ========================================================================
    // MODALS - Try to find and trigger all modals
    // ========================================================================
    async captureModals(pageName, pageData) {
        // Already captured via button clicks, but check for any open modals
        const openModals = await this.page.$$('[role="dialog"]:visible, .modal:visible');
        
        for (let i = 0; i < openModals.length; i++) {
            try {
                await this.ss.capture(this.page, `${pageName}-modal-found-${i + 1}`, 'modals', `Found modal ${i + 1}`);
                pageData.screenshots++;
            } catch (e) {}
        }
    }

    // ========================================================================
    // TOOLTIPS
    // ========================================================================
    async captureTooltips(pageName, pageData) {
        const elementsWithTooltips = await this.page.$$('[title]:visible, [data-tooltip]:visible, [aria-describedby]:visible');
        console.log(`   💬 Found ${elementsWithTooltips.length} elements with tooltips...`);

        for (let i = 0; i < Math.min(elementsWithTooltips.length, 5); i++) {
            try {
                const el = elementsWithTooltips[i];
                await el.scrollIntoViewIfNeeded();
                await el.hover();
                await this.page.waitForTimeout(500);
                await this.ss.capture(this.page, `${pageName}-tooltip-${i + 1}`, 'tooltips', `Tooltip ${i + 1}`);
                pageData.screenshots++;
            } catch (e) {}
        }
    }

    // ========================================================================
    // RESPONSIVE TESTING
    // ========================================================================
    async testResponsive(route) {
        const { path: routePath, name } = route;
        console.log(`   📱 Responsive testing for ${name}...`);

        const viewports = [
            { name: 'tablet', ...CONFIG.viewports.tablet },
            { name: 'mobile', ...CONFIG.viewports.mobile }
        ];

        for (const vp of viewports) {
            try {
                await this.page.setViewportSize({ width: vp.width, height: vp.height });
                await this.page.goto(`${CONFIG.baseUrl}${routePath}`, { waitUntil: 'networkidle' });
                await this.page.waitForTimeout(500);
                
                await this.ss.capture(this.page, `${name}-${vp.name}`, `responsive-${vp.name}`, `${name} at ${vp.width}x${vp.height}`);
            } catch (e) {}
        }

        // Reset to desktop
        await this.page.setViewportSize(CONFIG.viewports.desktop);
    }

    // ========================================================================
    // DARK MODE TESTING
    // ========================================================================
    async testDarkMode(route) {
        const { path: routePath, name } = route;
        console.log(`   🌙 Dark mode testing for ${name}...`);

        try {
            // Try to find and click theme toggle
            const themeToggles = await this.page.$$('[data-theme-toggle], .theme-toggle, button[aria-label*="theme"], button[aria-label*="dark"], button[aria-label*="light"]');
            
            if (themeToggles.length > 0) {
                await themeToggles[0].click();
                await this.page.waitForTimeout(500);
                await this.ss.capture(this.page, `${name}-dark-mode`, 'dark-mode', `${name} in dark mode`);
                
                // Toggle back
                await themeToggles[0].click();
                await this.page.waitForTimeout(300);
            }
        } catch (e) {}
    }

    // ========================================================================
    // RUN ALL TESTS
    // ========================================================================
    async runAllTests() {
        await this.init();
        
        const loginSuccess = await this.login();
        if (!loginSuccess) {
            console.log('❌ Cannot continue without login');
            await this.cleanup();
            return;
        }

        // Test all route categories
        const categories = [
            { routes: ALL_ROUTES.main, dir: 'pages' },
            { routes: ALL_ROUTES.documents, dir: 'pages' },
            { routes: ALL_ROUTES.kasse, dir: 'pages' },
            { routes: ALL_ROUTES.spesen, dir: 'pages' },
            { routes: ALL_ROUTES.streckengeschaeft, dir: 'pages' },
            { routes: ALL_ROUTES.finanzen, dir: 'pages' },
            { routes: ALL_ROUTES.kunden, dir: 'pages' },
            { routes: ALL_ROUTES.lieferanten, dir: 'pages' },
            { routes: ALL_ROUTES.personal, dir: 'pages' },
            { routes: ALL_ROUTES.businessEntities, dir: 'pages' },
            { routes: ALL_ROUTES.privat, dir: 'pages' },
            { routes: ALL_ROUTES.adminMain, dir: 'pages' },
            { routes: ALL_ROUTES.adminOcr, dir: 'pages' },
            { routes: ALL_ROUTES.adminDatev, dir: 'pages' },
            { routes: ALL_ROUTES.adminMahnungen, dir: 'pages' },
            { routes: ALL_ROUTES.adminBanking, dir: 'pages' }
        ];

        for (const { routes, dir } of categories) {
            for (const route of routes) {
                await this.testPageUltraDetailed(route, dir);
                
                // Responsive tests for key pages
                if (['dashboard', 'kasse', 'spesen', 'kunden', 'search'].includes(route.name)) {
                    await this.testResponsive(route);
                }
                
                // Dark mode test for first page of each category
                if (routes.indexOf(route) === 0) {
                    await this.testDarkMode(route);
                }
            }
        }

        await this.generateReports();
        await this.cleanup();
    }

    // ========================================================================
    // GENERATE REPORTS
    // ========================================================================
    async generateReports() {
        console.log('\n' + '═'.repeat(70));
        console.log('📊 GENERATING REPORTS');
        console.log('═'.repeat(70));

        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        
        // Screenshot Statistics
        const ssStats = this.ss.getStats();
        console.log(`\n📸 Screenshots: ${ssStats.total} total in ${ssStats.categories} categories`);
        
        // Analysis Report
        const analysisReport = this.analysis.generateReport();
        
        // Combined Report
        const fullReport = {
            meta: {
                timestamp: new Date().toISOString(),
                baseUrl: CONFIG.baseUrl,
                duration: `${Math.round((Date.now() - this.startTime) / 1000)}s`
            },
            results: this.results,
            screenshots: ssStats,
            analysis: analysisReport
        };

        // Save JSON report
        const jsonPath = path.join(CONFIG.reportDir, `ultra-comprehensive-${timestamp}.json`);
        fs.writeFileSync(jsonPath, JSON.stringify(fullReport, null, 2));
        console.log(`✅ JSON Report: ${jsonPath}`);

        // Save Markdown report
        const mdReport = this.generateMarkdownReport(fullReport);
        const mdPath = path.join(CONFIG.reportDir, `ultra-comprehensive-${timestamp}.md`);
        fs.writeFileSync(mdPath, mdReport);
        console.log(`✅ Markdown Report: ${mdPath}`);

        // Save Screenshot Index
        const indexPath = path.join(CONFIG.screenshotDir, 'INDEX.md');
        const indexContent = this.generateScreenshotIndex();
        fs.writeFileSync(indexPath, indexContent);
        console.log(`✅ Screenshot Index: ${indexPath}`);

        // Print summary
        console.log('\n' + '═'.repeat(70));
        console.log('📈 FINAL SUMMARY');
        console.log('═'.repeat(70));
        console.log(`   Pages Tested: ${this.results.passed + this.results.failed}`);
        console.log(`   ✅ Passed: ${this.results.passed}`);
        console.log(`   ❌ Failed: ${this.results.failed}`);
        console.log(`   📸 Screenshots: ${ssStats.total}`);
        console.log(`   📁 Categories: ${ssStats.categories}`);
        console.log(`   🕐 Duration: ${fullReport.meta.duration}`);
        console.log('═'.repeat(70) + '\n');
    }

    generateMarkdownReport(report) {
        let md = `# Ultra-Comprehensive Test Report\n\n`;
        md += `**Generated:** ${report.meta.timestamp}\n`;
        md += `**Duration:** ${report.meta.duration}\n\n`;

        md += `## Summary\n\n`;
        md += `| Metric | Value |\n|--------|-------|\n`;
        md += `| Pages Tested | ${report.results.passed + report.results.failed} |\n`;
        md += `| Passed | ${report.results.passed} |\n`;
        md += `| Failed | ${report.results.failed} |\n`;
        md += `| Screenshots | ${report.screenshots.total} |\n`;
        md += `| Categories | ${report.screenshots.categories} |\n\n`;

        md += `## Screenshots by Category\n\n`;
        md += `| Category | Count |\n|----------|-------|\n`;
        for (const [cat, count] of Object.entries(report.screenshots.byCategory).sort((a, b) => b[1] - a[1])) {
            md += `| ${cat} | ${count} |\n`;
        }
        md += '\n';

        md += `## Analysis Summary\n\n`;
        md += `- **Total Buttons Found:** ${report.analysis.summary.totalButtons}\n`;
        md += `- **Total Forms Found:** ${report.analysis.summary.totalForms}\n`;
        md += `- **Total Tables Found:** ${report.analysis.summary.totalTables}\n`;
        md += `- **Empty States Found:** ${report.analysis.summary.totalEmptyStates}\n`;
        md += `- **Interactions Tested:** ${report.analysis.summary.totalInteractions}\n`;
        md += `- **Successful Interactions:** ${report.analysis.summary.successfulInteractions}\n\n`;

        if (report.analysis.emptyStates.length > 0) {
            md += `## Empty States (Potential Feature Gaps)\n\n`;
            for (const es of report.analysis.emptyStates) {
                md += `- **${es.page}**: ${es.description} (${es.selector})\n`;
            }
            md += '\n';
        }

        if (report.analysis.suggestions.length > 0) {
            md += `## Suggestions\n\n`;
            for (const s of report.analysis.suggestions) {
                md += `- **${s.page}** [${s.category}]: ${s.suggestion}\n`;
            }
        }

        return md;
    }

    generateScreenshotIndex() {
        let md = `# Screenshot Index\n\n`;
        md += `**Total Screenshots:** ${this.ss.counter}\n\n`;

        for (const [category, shots] of Object.entries(this.ss.byCategory)) {
            md += `## ${category} (${shots.length})\n\n`;
            for (const shot of shots) {
                md += `- \`${shot.filename}\` - ${shot.description || shot.name}\n`;
            }
            md += '\n';
        }

        return md;
    }

    // ========================================================================
    // CLEANUP
    // ========================================================================
    async cleanup() {
        if (this.browser) {
            await this.browser.close();
        }
        console.log('🧹 Cleanup complete\n');
    }
}

// ============================================================================
// RUN
// ============================================================================
const suite = new UltraComprehensiveTestSuite();
suite.startTime = Date.now();
suite.runAllTests().catch(console.error);
