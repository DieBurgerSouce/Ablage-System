/**
 * ============================================================================
 * ABLAGE-SYSTEM ULTRA-COMPREHENSIVE E2E TEST SUITE V2
 * ============================================================================
 *
 * VERBESSERTE VERSION mit:
 * - Theme-Tests (Light, Dark, Whitescreen, Blackscreen)
 * - Button-Click-Ergebnisse
 * - Form-Validation-Tests
 * - shadcn/ui Card-Erkennung
 * - Chart/Graph-Erkennung
 * - Pagination-Tests
 * - Confirmation-Dialog-Tests
 * - Toast-Erkennung (Sonner)
 *
 * Ziel: 1500+ Screenshots in ALLEN 73 Kategorien
 *
 * Author: Ben / UFI Digital Agency
 * Created: 2025-12-31
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
// ALL ROUTES - 57+ pages
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
        { path: '/document-groups', name: 'document-groups' },
        // Dynamic routes with real IDs from database
        { path: '/document-groups/4ed3e5e2-97a3-4e58-990e-baea58c9ba26', name: 'document-group-detail' },
        { path: '/documents/02290492-dc23-4a59-a3cf-b09640802f7a', name: 'document-detail' },
        { path: '/documents/02290492-dc23-4a59-a3cf-b09640802f7a/relationships', name: 'document-relationships' },
        { path: '/validation-queue/02290492-dc23-4a59-a3cf-b09640802f7a', name: 'validation-queue-detail' }
    ],
    kasse: [
        { path: '/kasse', name: 'kasse' },
        { path: '/kasse/buch/ee8c7d79-8e32-4899-b63a-3a09af1569f2', name: 'kasse-buch-detail' }
    ],
    spesen: [
        { path: '/spesen', name: 'spesen' },
        { path: '/spesen/d2c2c39d-d3e7-45dd-9566-769860894366', name: 'spesen-report-detail' }
    ],
    streckengeschaeft: [
        { path: '/streckengeschaeft', name: 'streckengeschaeft' },
        { path: '/streckengeschaeft/zm', name: 'streckengeschaeft-zm' }
    ],
    finanzen: [
        { path: '/finanzen', name: 'finanzen' },
        { path: '/finanzen/2025', name: 'finanzen-2025' },
        { path: '/finanzen/2024', name: 'finanzen-2024' },
        { path: '/finanzen/2025/einnahmen', name: 'finanzen-2025-einnahmen' },
        { path: '/finanzen/2025/ausgaben', name: 'finanzen-2025-ausgaben' },
        { path: '/finanzen/2025/rechnungen', name: 'finanzen-2025-rechnungen' }
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
        { path: '/business-entities', name: 'business-entities' },
        { path: '/business-entities/new', name: 'business-entities-new' }
    ],
    privat: [
        { path: '/privat', name: 'privat' },
        { path: '/privat/finanzen', name: 'privat-finanzen' },
        { path: '/privat/notfall', name: 'privat-notfall' },
        { path: '/privat/fahrzeuge', name: 'privat-fahrzeuge' },
        { path: '/privat/fristen', name: 'privat-fristen' },
        { path: '/privat/immobilien', name: 'privat-immobilien' },
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
// THEME MODES - 4 Display-Modi
// ============================================================================
const THEME_MODES = [
    { name: 'light', label: 'Hell', selector: 'button:has-text("Hell"):not(:has-text("Hellmodus"))' },
    { name: 'dark', label: 'Dunkel', selector: 'button:has-text("Dunkel")' },
    { name: 'whitescreen', label: 'Hoher Kontrast', selector: 'button:has-text("Hoher Kontrast")' },
    { name: 'blackscreen', label: 'OLED-Modus', selector: 'button:has-text("OLED-Modus")' }
];

// ============================================================================
// SCREENSHOT MANAGER
// ============================================================================
class ScreenshotManager {
    constructor(baseDir) {
        this.baseDir = baseDir;
        this.counter = 0;
        this.screenshots = [];
        this.byCategory = {};
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
                await page.screenshot({ path: filepath, fullPage: false });
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
// MAIN TEST SUITE V2
// ============================================================================
class UltraComprehensiveTestSuiteV2 {
    constructor() {
        this.browser = null;
        this.context = null;
        this.page = null;
        this.ss = null;
        this.results = { passed: 0, failed: 0, skipped: 0 };
        this.startTime = Date.now();
        this.currentTheme = 'dark'; // Default theme
        this.lastLoginTime = Date.now();
        this.sessionRefreshInterval = 20 * 60 * 1000; // 20 minutes
    }

    // ========================================================================
    // SESSION REFRESH - Prevents session timeout during long tests
    // ========================================================================
    async refreshSessionIfNeeded() {
        const now = Date.now();
        if (now - this.lastLoginTime > this.sessionRefreshInterval) {
            console.log('🔄 Refreshing session to prevent timeout...');
            try {
                await this.login();
                this.lastLoginTime = Date.now();
                console.log('✅ Session refreshed\n');
            } catch (e) {
                console.log('⚠️ Session refresh failed, continuing anyway');
            }
        }
    }

    async init() {
        console.log('\n' + '═'.repeat(70));
        console.log('🚀 ULTRA-COMPREHENSIVE TEST SUITE V2');
        console.log('   - Theme Tests (4 Modi)');
        console.log('   - Button Click Results');
        console.log('   - Form Validation');
        console.log('   - Card/Chart Detection');
        console.log('═'.repeat(70));
        console.log(`📁 Screenshots: ${CONFIG.screenshotDir}`);
        console.log(`🌐 Base URL: ${CONFIG.baseUrl}`);
        console.log('═'.repeat(70) + '\n');

        // Create ALL directories
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
            'dark-mode', 'light-mode', 'whitescreen-mode', 'blackscreen-mode',
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

        await this.ss.capture(this.page, 'login-page-initial', 'pages');

        // Use keyboard.type() instead of fill() for React controlled inputs
        const emailField = await this.page.$('#email');
        const passwordField = await this.page.$('#password');

        if (emailField && passwordField) {
            await emailField.click();
            await this.page.keyboard.type(CONFIG.credentials.email, { delay: 30 });

            await passwordField.click();
            await this.page.keyboard.type(CONFIG.credentials.password, { delay: 30 });
        } else {
            console.log('   ⚠️ Login fields not found');
            return false;
        }

        await this.ss.capture(this.page, 'login-page-filled', 'forms-filled');

        await this.page.click('button[type="submit"]');
        await this.page.waitForTimeout(3000);

        const currentUrl = this.page.url();
        if (!currentUrl.includes('/login')) {
            console.log('✅ Login successful\n');
            await this.ss.capture(this.page, 'after-login-dashboard', 'pages');
            return true;
        }

        await this.ss.capture(this.page, 'login-failed', 'errors');
        console.log('❌ Login failed\n');
        return false;
    }

    // ========================================================================
    // THEME TESTS - ALLE 4 MODI
    // ========================================================================
    async testAllThemeModes(pageName) {
        console.log(`   🎨 Testing all theme modes...`);

        try {
            // Öffne Settings Modal via Sidebar Button
            const settingsBtn = await this.page.$('button:has-text("Einstellungen")');
            if (!settingsBtn) {
                console.log(`      ⚠️ Settings button not found`);
                return;
            }
            await settingsBtn.click();
            await this.page.waitForTimeout(800);

            // Warte auf Modal
            const modal = await this.page.$('[role="dialog"]');
            if (!modal) {
                console.log(`      ⚠️ Settings modal not opened`);
                return;
            }
            await this.ss.capture(this.page, `${pageName}-settings-modal`, 'modals');

            // Klicke auf "Anzeige" Tab
            const displayTab = await this.page.$('button[role="tab"]:has-text("Anzeige"), button:has-text("Anzeige")');
            if (displayTab) {
                await displayTab.click();
                await this.page.waitForTimeout(500);
                await this.ss.capture(this.page, `${pageName}-display-tab`, 'tabs');
            }

            // Teste alle Theme-Modi
            for (const theme of THEME_MODES) {
                try {
                    // Finde Theme-Button im Modal
                    const themeBtn = await this.page.$(`[role="dialog"] button:has-text("${theme.label}")`);

                    if (themeBtn && await themeBtn.isVisible()) {
                        await themeBtn.click();
                        await this.page.waitForTimeout(600);

                        // Screenshot des Modals im neuen Theme
                        await this.ss.capture(this.page, `${pageName}-${theme.name}-modal`, `${theme.name}-mode`);
                        this.currentTheme = theme.name;
                        console.log(`      ✓ ${theme.label} mode captured`);
                    }
                } catch (e) {
                    console.log(`      ⚠️ Theme ${theme.label} failed: ${e.message}`);
                }
            }

            // Zurück zu Dark Mode
            try {
                const darkBtn = await this.page.$('[role="dialog"] button:has-text("Dunkel")');
                if (darkBtn && await darkBtn.isVisible()) {
                    await darkBtn.click();
                    await this.page.waitForTimeout(300);
                }
            } catch (e) {}

            // Modal schließen (Escape oder X klicken)
            try {
                await this.page.keyboard.press('Escape');
                await this.page.waitForTimeout(300);
            } catch (e) {}

        } catch (e) {
            console.log(`      ⚠️ Theme testing failed: ${e.message}`);
        }
    }

    // ========================================================================
    // CARDS ERKENNEN (shadcn/ui)
    // ========================================================================
    async captureAllCards(pageName) {
        const cardSelectors = [
            '[class*="rounded-lg"][class*="border"][class*="bg-card"]',
            '[class*="rounded-xl"][class*="border"]',
            'div[class*="shadow"][class*="rounded-lg"]',
            '.card',
            '[data-card]'
        ];

        let cardCount = 0;
        for (const selector of cardSelectors) {
            try {
                const cards = await this.page.$$(selector);
                for (let i = 0; i < Math.min(cards.length, 10); i++) {
                    const card = cards[i];
                    if (await card.isVisible()) {
                        await card.scrollIntoViewIfNeeded();
                        cardCount++;
                        await this.ss.capture(this.page, `${pageName}-card-${cardCount}`, 'cards', `Card ${cardCount}`, card);
                    }
                }
            } catch (e) {}
        }

        if (cardCount > 0) {
            console.log(`   🃏 Found ${cardCount} cards`);
        }
        return cardCount;
    }

    // ========================================================================
    // CHARTS ERKENNEN
    // ========================================================================
    async captureAllCharts(pageName) {
        const chartSelectors = [
            '.recharts-wrapper',
            'svg.recharts-surface',
            '[class*="chart"]',
            'canvas',
            '.apexcharts-canvas',
            '[data-chart]'
        ];

        let chartCount = 0;
        for (const selector of chartSelectors) {
            try {
                const charts = await this.page.$$(selector);
                for (let i = 0; i < Math.min(charts.length, 5); i++) {
                    const chart = charts[i];
                    if (await chart.isVisible()) {
                        await chart.scrollIntoViewIfNeeded();
                        chartCount++;
                        await this.ss.capture(this.page, `${pageName}-chart-${chartCount}`, 'charts', `Chart ${chartCount}`);
                    }
                }
            } catch (e) {}
        }

        if (chartCount > 0) {
            console.log(`   📊 Found ${chartCount} charts`);
        }
        return chartCount;
    }

    // ========================================================================
    // BUTTONS MIT CLICK-ERGEBNISSEN
    // ========================================================================
    async captureAllButtonsWithResults(pageName) {
        const buttons = await this.page.$$('button:visible');
        console.log(`   🔘 Testing ${buttons.length} buttons...`);

        let btnIndex = 0;
        const safePatterns = ['Neu', 'Erstellen', 'Add', 'New', 'Create', 'Filter', 'Suchen', 'Aktualisieren', 'Refresh', 'Speichern', 'Save'];
        const dangerPatterns = ['Löschen', 'Delete', 'Entfernen', 'Remove'];

        for (const btn of buttons.slice(0, 25)) {
            btnIndex++;
            try {
                const text = ((await btn.textContent()) || '').trim().substring(0, 25);
                const isDisabled = await btn.isDisabled();

                await btn.scrollIntoViewIfNeeded();

                // Normal state
                await this.ss.capture(this.page, `${pageName}-btn-${btnIndex}-${text || 'icon'}`, 'buttons');

                // Hover state
                await btn.hover();
                await this.page.waitForTimeout(200);
                await this.ss.capture(this.page, `${pageName}-btn-${btnIndex}-hover`, 'buttons-hover');

                // Click safe buttons
                const isSafe = safePatterns.some(p => text.toLowerCase().includes(p.toLowerCase()));
                const isDanger = dangerPatterns.some(p => text.toLowerCase().includes(p.toLowerCase()));

                if (isSafe && !isDanger && !isDisabled) {
                    await btn.click();
                    await this.page.waitForTimeout(500);

                    // Screenshot after click
                    await this.ss.capture(this.page, `${pageName}-btn-${btnIndex}-clicked`, 'buttons-clicked');

                    // Check for Toast (Sonner)
                    const toast = await this.page.$('[data-sonner-toast], [data-sonner-toaster] > *, ol[data-sonner-toaster] li');
                    if (toast) {
                        await this.ss.capture(this.page, `${pageName}-toast-${btnIndex}`, 'toasts');
                    }

                    // Check for Success message
                    const success = await this.page.$(':has-text("Erfolgreich"), :has-text("gespeichert"), :has-text("erstellt")');
                    if (success && await success.isVisible()) {
                        await this.ss.capture(this.page, `${pageName}-success-${btnIndex}`, 'success-states');
                    }

                    // Check for Modal
                    const modal = await this.page.$('[role="dialog"]:visible');
                    if (modal) {
                        await this.ss.capture(this.page, `${pageName}-modal-from-btn-${btnIndex}`, 'modals');

                        // Close modal
                        await this.page.keyboard.press('Escape');
                        await this.page.waitForTimeout(300);
                    }
                }

                // Danger buttons - trigger confirmation dialog
                if (isDanger && !isDisabled) {
                    await btn.click();
                    await this.page.waitForTimeout(300);

                    const confirmDialog = await this.page.$('[role="alertdialog"], [role="dialog"]:has-text("Löschen"), [role="dialog"]:has-text("Entfernen")');
                    if (confirmDialog) {
                        await this.ss.capture(this.page, `${pageName}-confirmation-${btnIndex}`, 'confirmations');

                        // Cancel
                        const cancelBtn = await this.page.$('button:has-text("Abbrechen"), button:has-text("Nein")');
                        if (cancelBtn) {
                            await cancelBtn.click();
                            await this.page.waitForTimeout(200);
                        } else {
                            await this.page.keyboard.press('Escape');
                            await this.page.waitForTimeout(200);
                        }
                    }
                }

            } catch (e) {}
        }
    }

    // ========================================================================
    // FORM VALIDATION TESTEN
    // ========================================================================
    async testFormValidation(pageName) {
        const forms = await this.page.$$('form:visible');
        console.log(`   📝 Testing ${forms.length} forms for validation...`);

        let formIndex = 0;
        for (const form of forms) {
            formIndex++;
            try {
                await form.scrollIntoViewIfNeeded();

                // Empty state
                await this.ss.capture(this.page, `${pageName}-form-${formIndex}-empty`, 'forms-empty');

                // Try to submit empty form to trigger validation
                const submitBtn = await form.$('button[type="submit"]');
                if (submitBtn && !await submitBtn.isDisabled()) {
                    await submitBtn.click();
                    await this.page.waitForTimeout(300);

                    // Check for validation errors
                    const errors = await form.$$('[aria-invalid="true"], .text-destructive, [data-invalid], .error');
                    if (errors.length > 0) {
                        await this.ss.capture(this.page, `${pageName}-form-${formIndex}-validation-errors`, 'forms-validation');
                        console.log(`      ✓ Form ${formIndex}: ${errors.length} validation errors captured`);
                    }
                }

                // Fill with invalid email to trigger validation
                const emailInput = await form.$('input[type="email"]');
                if (emailInput && !await emailInput.isDisabled()) {
                    await emailInput.fill('ungültige-email');
                    await emailInput.blur();
                    await this.page.waitForTimeout(200);

                    const emailError = await form.$('[aria-invalid="true"], .text-destructive');
                    if (emailError) {
                        await this.ss.capture(this.page, `${pageName}-form-${formIndex}-invalid-email`, 'forms-validation');
                    }

                    // Clear invalid input
                    await emailInput.fill('');
                }

                // Fill form with valid data
                const inputs = await form.$$('input:visible, textarea:visible');
                for (const input of inputs) {
                    try {
                        const type = await input.getAttribute('type');
                        const name = await input.getAttribute('name') || '';
                        const isDisabled = await input.isDisabled();
                        if (isDisabled) continue;

                        if (type === 'email') await input.fill('test@example.com');
                        else if (type === 'password') await input.fill('Test123!');
                        else if (type === 'date') await input.fill('2025-12-31');
                        else if (type === 'number') await input.fill('100');
                        else if (type === 'tel') await input.fill('+49 123 456789');
                        else if (name.includes('iban')) await input.fill('DE89370400440532013000');
                        else if (name.includes('amount') || name.includes('betrag')) await input.fill('123.45');
                        else if (name.includes('title') || name.includes('name')) await input.fill('Test Eintrag');
                        else if (type !== 'checkbox' && type !== 'radio') await input.fill('Test Eingabe');
                    } catch (e) {}
                }

                await this.ss.capture(this.page, `${pageName}-form-${formIndex}-filled`, 'forms-filled');

            } catch (e) {}
        }
    }

    // ========================================================================
    // PAGINATION TESTEN
    // ========================================================================
    async testPagination(pageName) {
        const paginationSelectors = [
            '[aria-label*="pagination"]',
            'nav:has(button:has-text("Weiter"))',
            'nav:has(button:has-text("Zurück"))',
            'div:has(button:has-text("Seite"))',
            '.pagination'
        ];

        for (const selector of paginationSelectors) {
            try {
                const pagination = await this.page.$(selector);
                if (pagination && await pagination.isVisible()) {
                    await pagination.scrollIntoViewIfNeeded();
                    await this.ss.capture(this.page, `${pageName}-pagination`, 'pagination');

                    // Try next page
                    const nextBtn = await this.page.$('button:has-text("Weiter"), button[aria-label*="Next"], button:has-text(">")');
                    if (nextBtn && !await nextBtn.isDisabled()) {
                        await nextBtn.click();
                        await this.page.waitForTimeout(500);
                        await this.ss.capture(this.page, `${pageName}-pagination-page2`, 'pagination');

                        // Go back
                        const prevBtn = await this.page.$('button:has-text("Zurück"), button[aria-label*="Previous"]');
                        if (prevBtn) {
                            await prevBtn.click();
                            await this.page.waitForTimeout(300);
                        }
                    }

                    console.log(`   📄 Pagination found and tested`);
                    return true;
                }
            } catch (e) {}
        }
        return false;
    }

    // ========================================================================
    // TABLES TESTEN
    // ========================================================================
    async captureAllTables(pageName) {
        const tables = await this.page.$$('table:visible, [role="grid"]:visible');
        console.log(`   📊 Testing ${tables.length} tables...`);

        let tableIndex = 0;
        for (const table of tables) {
            tableIndex++;
            try {
                await table.scrollIntoViewIfNeeded();
                await this.ss.capture(this.page, `${pageName}-table-${tableIndex}`, 'tables');

                const rows = await table.$$('tbody tr, [role="row"]');
                if (rows.length === 0) {
                    await this.ss.capture(this.page, `${pageName}-table-${tableIndex}-empty`, 'tables-empty');
                } else {
                    // Capture rows with hover
                    for (let i = 0; i < Math.min(3, rows.length); i++) {
                        const row = rows[i];
                        await row.hover();
                        await this.page.waitForTimeout(200);
                        await this.ss.capture(this.page, `${pageName}-table-${tableIndex}-row-${i + 1}`, 'tables-rows');

                        // Check for row actions
                        const actions = await row.$$('button, [data-action]');
                        if (actions.length > 0) {
                            await this.ss.capture(this.page, `${pageName}-table-${tableIndex}-row-${i + 1}-actions`, 'tables-actions');
                        }
                    }
                }

                // Test sorting if available
                const sortHeaders = await table.$$('th[aria-sort], th button, [role="columnheader"] button');
                if (sortHeaders.length > 0 && sortHeaders[0]) {
                    await sortHeaders[0].click();
                    await this.page.waitForTimeout(300);
                    await this.ss.capture(this.page, `${pageName}-table-${tableIndex}-sorted`, 'sorting');
                }

            } catch (e) {}
        }
    }

    // ========================================================================
    // TABS TESTEN
    // ========================================================================
    async captureAllTabs(pageName) {
        const tabLists = await this.page.$$('[role="tablist"]:visible');
        console.log(`   🗂️ Testing ${tabLists.length} tab groups...`);

        let tabGroupIndex = 0;
        for (const tabList of tabLists) {
            tabGroupIndex++;
            try {
                const tabs = await tabList.$$('[role="tab"]');
                for (let i = 0; i < tabs.length; i++) {
                    const tab = tabs[i];
                    const tabText = ((await tab.textContent()) || '').trim().substring(0, 20);

                    await tab.click();
                    await this.page.waitForTimeout(300);
                    await this.ss.capture(this.page, `${pageName}-tab-${tabGroupIndex}-${i + 1}-${tabText}`, 'tabs');

                    const tabPanel = await this.page.$('[role="tabpanel"]:visible');
                    if (tabPanel) {
                        await this.ss.capture(this.page, `${pageName}-tab-${tabGroupIndex}-${i + 1}-content`, 'tabs-content');
                    }
                }
            } catch (e) {}
        }
    }

    // ========================================================================
    // DROPDOWNS TESTEN
    // ========================================================================
    async captureAllDropdowns(pageName) {
        const dropdownTriggers = await this.page.$$('[aria-haspopup="true"], [aria-haspopup="listbox"], [aria-haspopup="menu"]');
        console.log(`   📋 Testing ${dropdownTriggers.length} dropdowns...`);

        let ddIndex = 0;
        for (const trigger of dropdownTriggers.slice(0, 10)) {
            ddIndex++;
            try {
                await trigger.scrollIntoViewIfNeeded();
                await this.ss.capture(this.page, `${pageName}-dropdown-${ddIndex}-closed`, 'dropdowns');

                await trigger.click();
                await this.page.waitForTimeout(300);
                await this.ss.capture(this.page, `${pageName}-dropdown-${ddIndex}-open`, 'dropdowns-open');

                const options = await this.page.$$('[role="option"]:visible, [role="menuitem"]:visible');
                if (options.length > 0) {
                    await this.ss.capture(this.page, `${pageName}-dropdown-${ddIndex}-options`, 'dropdowns-options');
                }

                await this.page.keyboard.press('Escape');
                await this.page.waitForTimeout(200);

            } catch (e) {}
        }
    }

    // ========================================================================
    // EMPTY STATES (called per page)
    // ========================================================================
    async captureEmptyStates(pageName) {
        await this.captureEmptyStatesOnPage(pageName);
    }

    // ========================================================================
    // DEDICATED EMPTY STATE TESTS - Targets specific empty state scenarios
    // ========================================================================
    async runEmptyStateTests() {
        console.log('   Testing dedicated empty states...');

        // 1. Search with no results
        try {
            await this.page.goto(`${CONFIG.baseUrl}/search`, { waitUntil: 'networkidle' });
            await this.page.waitForTimeout(1000);

            const searchInput = await this.page.$('input[type="search"], input[placeholder*="Such"], input[name="query"]');
            if (searchInput) {
                await searchInput.fill('xyznonexistent12345');
                await this.page.keyboard.press('Enter');
                await this.page.waitForTimeout(2000);
                await this.ss.capture(this.page, 'search-no-results', 'search-empty');
                console.log('   ✅ Search empty state captured');
            }
        } catch (e) {
            console.log(`   ⚠️ Search empty state failed: ${e.message}`);
        }

        // 2. Filter with no results on documents page
        try {
            await this.page.goto(`${CONFIG.baseUrl}/`, { waitUntil: 'networkidle' });
            await this.page.waitForTimeout(1000);

            const filterBtn = await this.page.$('button:has-text("Filter"), [aria-label*="Filter"]');
            if (filterBtn) {
                await filterBtn.click();
                await this.page.waitForTimeout(500);
                await this.ss.capture(this.page, 'filter-panel-open', 'filters');

                // Try to set impossible filter
                const dateInput = await this.page.$('input[type="date"]');
                if (dateInput) {
                    await dateInput.fill('1900-01-01');
                    await this.page.waitForTimeout(1000);
                    await this.ss.capture(this.page, 'filter-no-results', 'filters-applied');
                }
            }
        } catch (e) {
            console.log(`   ⚠️ Filter empty state failed: ${e.message}`);
        }

        // 3. Empty tables on various pages
        const emptyTablePages = [
            { path: '/admin/job-queue', name: 'job-queue' },
            { path: '/validation-queue', name: 'validation-queue' },
            { path: '/streckengeschaeft', name: 'streckengeschaeft' }
        ];

        for (const { path: pagePath, name: pageName } of emptyTablePages) {
            try {
                await this.page.goto(`${CONFIG.baseUrl}${pagePath}`, { waitUntil: 'networkidle' });
                await this.page.waitForTimeout(1500);

                const table = await this.page.$('table, [role="grid"]');
                if (table) {
                    const rows = await table.$$('tbody tr');
                    if (rows.length === 0 || rows.length === 1) {
                        await this.ss.capture(this.page, `${pageName}-table-empty`, 'tables-empty');
                        console.log(`   ✅ Empty table captured: ${pageName}`);
                    }
                }

                // Also check for explicit empty state messages
                const emptyMessage = await this.page.$('text=Keine Einträge, text=Keine Daten, text=Leer');
                if (emptyMessage) {
                    await this.ss.capture(this.page, `${pageName}-empty-message`, 'empty-states');
                }
            } catch (e) {
                console.log(`   ⚠️ Empty table test failed for ${pageName}: ${e.message}`);
            }
        }

        // 4. Form validation errors
        try {
            await this.page.goto(`${CONFIG.baseUrl}/spesen`, { waitUntil: 'networkidle' });
            await this.page.waitForTimeout(1000);

            // Try to open create dialog
            const createBtn = await this.page.$('button:has-text("Neu"), button:has-text("Erstellen"), button:has-text("Hinzufügen")');
            if (createBtn) {
                await createBtn.click();
                await this.page.waitForTimeout(1000);

                // Try to submit empty form
                const submitBtn = await this.page.$('button[type="submit"], button:has-text("Speichern")');
                if (submitBtn) {
                    await submitBtn.click();
                    await this.page.waitForTimeout(500);
                    await this.ss.capture(this.page, 'spesen-form-validation-errors', 'forms-validation');
                    console.log('   ✅ Form validation errors captured');
                }

                // Close dialog
                await this.page.keyboard.press('Escape');
            }
        } catch (e) {
            console.log(`   ⚠️ Form validation test failed: ${e.message}`);
        }

        // 5. Dropdown options
        try {
            await this.page.goto(`${CONFIG.baseUrl}/kasse`, { waitUntil: 'networkidle' });
            await this.page.waitForTimeout(1000);

            const dropdowns = await this.page.$$('[aria-haspopup="listbox"], [role="combobox"]');
            for (let i = 0; i < Math.min(3, dropdowns.length); i++) {
                try {
                    await dropdowns[i].click();
                    await this.page.waitForTimeout(300);
                    await this.ss.capture(this.page, `kasse-dropdown-${i + 1}-options`, 'dropdowns-options');
                    await this.page.keyboard.press('Escape');
                } catch (e) {}
            }
            console.log('   ✅ Dropdown options captured');
        } catch (e) {
            console.log(`   ⚠️ Dropdown options test failed: ${e.message}`);
        }

        // 6. Context menus / Action menus
        try {
            await this.page.goto(`${CONFIG.baseUrl}/`, { waitUntil: 'networkidle' });
            await this.page.waitForTimeout(1000);

            // Find action buttons (three dots menu)
            const actionBtns = await this.page.$$('button:has([class*="ellipsis"]), button:has([class*="dots"]), button[aria-label*="Aktionen"], button[aria-label*="Mehr"]');
            for (let i = 0; i < Math.min(3, actionBtns.length); i++) {
                try {
                    await actionBtns[i].click();
                    await this.page.waitForTimeout(300);
                    await this.ss.capture(this.page, `action-menu-${i + 1}`, 'action-menus');
                    await this.page.keyboard.press('Escape');
                } catch (e) {}
            }
            console.log('   ✅ Action menus captured');
        } catch (e) {
            console.log(`   ⚠️ Action menus test failed: ${e.message}`);
        }

        // 7. Breadcrumbs
        try {
            await this.page.goto(`${CONFIG.baseUrl}/finanzen/2025/einnahmen`, { waitUntil: 'networkidle' });
            await this.page.waitForTimeout(1000);

            const breadcrumb = await this.page.$('nav[aria-label*="Breadcrumb"], [class*="breadcrumb"], nav:has(a):has(span)');
            if (breadcrumb) {
                await this.ss.capture(this.page, 'breadcrumb-finanzen', 'breadcrumbs');
                console.log('   ✅ Breadcrumbs captured');
            }
        } catch (e) {
            console.log(`   ⚠️ Breadcrumbs test failed: ${e.message}`);
        }

        console.log('   📭 Empty state tests completed');
    }

    // Continuation of captureEmptyStates method
    async captureEmptyStatesOnPage(pageName) {
        const emptySelectors = [
            'text=Keine Daten', 'text=Keine Einträge', 'text=Noch keine',
            'text=Keine Ergebnisse', 'text=Leer', 'text=Keine Dokumente',
            'text=Nichts gefunden', '.empty-state', '[data-empty]'
        ];

        for (const selector of emptySelectors) {
            try {
                const elements = await this.page.$$(selector);
                for (let i = 0; i < elements.length; i++) {
                    const el = elements[i];
                    if (await el.isVisible()) {
                        await el.scrollIntoViewIfNeeded();
                        await this.ss.capture(this.page, `${pageName}-empty-${i + 1}`, 'empty-states');
                    }
                }
            } catch (e) {}
        }
    }

    // ========================================================================
    // ERROR STATES
    // ========================================================================
    async captureErrorStates(pageName) {
        const errorSelectors = [
            '.text-destructive', '[role="alert"]', '.error',
            'text=Fehler', 'text=fehlgeschlagen', '[data-error]'
        ];

        for (const selector of errorSelectors) {
            try {
                const elements = await this.page.$$(selector);
                for (let i = 0; i < elements.length; i++) {
                    const el = elements[i];
                    if (await el.isVisible()) {
                        await el.scrollIntoViewIfNeeded();
                        await this.ss.capture(this.page, `${pageName}-error-${i + 1}`, 'error-states');
                    }
                }
            } catch (e) {}
        }
    }

    // ========================================================================
    // LOADING STATES
    // ========================================================================
    async captureLoadingStates(pageName) {
        const loadingSelectors = ['.animate-spin', '.animate-pulse', '.skeleton', '[aria-busy="true"]', '.loading'];

        for (const selector of loadingSelectors) {
            try {
                const elements = await this.page.$$(selector);
                for (let i = 0; i < Math.min(elements.length, 3); i++) {
                    const el = elements[i];
                    if (await el.isVisible()) {
                        await this.ss.capture(this.page, `${pageName}-loading-${i + 1}`, 'loading-states');
                    }
                }
            } catch (e) {}
        }
    }

    // ========================================================================
    // SIDEBAR
    // ========================================================================
    async captureSidebar(pageName) {
        const sidebar = await this.page.$('aside, [data-sidebar], nav[role="navigation"]');
        if (sidebar && await sidebar.isVisible()) {
            await this.ss.capture(this.page, `${pageName}-sidebar`, 'sidebar');
        }
    }

    // ========================================================================
    // TOOLTIPS
    // ========================================================================
    async captureTooltips(pageName) {
        const elementsWithTooltips = await this.page.$$('[title]:visible, [data-tooltip]:visible');

        for (let i = 0; i < Math.min(elementsWithTooltips.length, 5); i++) {
            try {
                const el = elementsWithTooltips[i];
                await el.scrollIntoViewIfNeeded();
                await el.hover();
                await this.page.waitForTimeout(500);
                await this.ss.capture(this.page, `${pageName}-tooltip-${i + 1}`, 'tooltips');
            } catch (e) {}
        }
    }

    // ========================================================================
    // RESPONSIVE TESTS
    // ========================================================================
    async testResponsive(route) {
        const { path: routePath, name } = route;

        const viewports = [
            { name: 'tablet', ...CONFIG.viewports.tablet },
            { name: 'mobile', ...CONFIG.viewports.mobile }
        ];

        for (const vp of viewports) {
            try {
                await this.page.setViewportSize({ width: vp.width, height: vp.height });
                await this.page.goto(`${CONFIG.baseUrl}${routePath}`, { waitUntil: 'networkidle' });
                await this.page.waitForTimeout(500);

                await this.ss.capture(this.page, `${name}-${vp.name}`, `responsive-${vp.name}`);
            } catch (e) {}
        }

        await this.page.setViewportSize(CONFIG.viewports.desktop);
    }

    // ========================================================================
    // TEST SINGLE PAGE - COMPLETE
    // ========================================================================
    async testPageComplete(route, isFirstPage = false) {
        const { path: routePath, name } = route;

        console.log(`\n${'─'.repeat(60)}`);
        console.log(`📄 ${name.toUpperCase()} (${routePath})`);
        console.log('─'.repeat(60));

        try {
            await this.page.goto(`${CONFIG.baseUrl}${routePath}`, {
                waitUntil: 'networkidle',
                timeout: CONFIG.timeout.navigation
            });
            await this.page.waitForTimeout(CONFIG.timeout.short);

            // Page screenshots
            await this.ss.capture(this.page, `${name}-01-initial`, 'pages');
            await this.page.waitForTimeout(500);
            await this.ss.capture(this.page, `${name}-02-loaded`, 'pages-loaded');

            // All elements
            await this.captureSidebar(name);
            await this.captureAllCards(name);
            await this.captureAllCharts(name);
            await this.captureAllButtonsWithResults(name);
            await this.testFormValidation(name);
            await this.captureAllTables(name);
            await this.captureAllTabs(name);
            await this.captureAllDropdowns(name);
            await this.testPagination(name);
            await this.captureEmptyStates(name);
            await this.captureErrorStates(name);
            await this.captureLoadingStates(name);
            await this.captureTooltips(name);

            // Theme tests on first page of each category
            if (isFirstPage) {
                await this.testAllThemeModes(name);
            }

            // Final state
            await this.ss.capture(this.page, `${name}-99-final`, 'pages');

            this.results.passed++;
            console.log(`   ✅ PASS`);
            return true;

        } catch (error) {
            console.log(`   ❌ FAIL - ${error.message}`);
            await this.ss.capture(this.page, `${name}-ERROR`, 'errors');
            this.results.failed++;
            return false;
        }
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

        // Test all categories
        const categories = [
            { routes: ALL_ROUTES.main, name: 'main' },
            { routes: ALL_ROUTES.documents, name: 'documents' },
            { routes: ALL_ROUTES.kasse, name: 'kasse' },
            { routes: ALL_ROUTES.spesen, name: 'spesen' },
            { routes: ALL_ROUTES.streckengeschaeft, name: 'streckengeschaeft' },
            { routes: ALL_ROUTES.finanzen, name: 'finanzen' },
            { routes: ALL_ROUTES.kunden, name: 'kunden' },
            { routes: ALL_ROUTES.lieferanten, name: 'lieferanten' },
            { routes: ALL_ROUTES.personal, name: 'personal' },
            { routes: ALL_ROUTES.businessEntities, name: 'business' },
            { routes: ALL_ROUTES.privat, name: 'privat' },
            { routes: ALL_ROUTES.adminMain, name: 'admin' },
            { routes: ALL_ROUTES.adminOcr, name: 'ocr' },
            { routes: ALL_ROUTES.adminDatev, name: 'datev' },
            { routes: ALL_ROUTES.adminMahnungen, name: 'mahnungen' },
            { routes: ALL_ROUTES.adminBanking, name: 'banking' }
        ];

        for (const { routes, name: catName } of categories) {
            console.log(`\n${'═'.repeat(70)}`);
            console.log(`📁 CATEGORY: ${catName.toUpperCase()}`);
            console.log('═'.repeat(70));

            // Refresh session at the start of each category to prevent timeout
            await this.refreshSessionIfNeeded();

            for (let i = 0; i < routes.length; i++) {
                const route = routes[i];
                const isFirst = i === 0;
                await this.testPageComplete(route, isFirst);

                // Responsive tests for key pages
                if (['dashboard', 'kasse', 'spesen', 'kunden', 'search', 'admin-users'].includes(route.name)) {
                    await this.testResponsive(route);
                }
            }
        }

        // Run dedicated empty state tests
        console.log(`\n${'═'.repeat(70)}`);
        console.log('📭 DEDICATED EMPTY STATE TESTS');
        console.log('═'.repeat(70));
        await this.runEmptyStateTests();

        await this.generateReports();
        await this.cleanup();
    }

    // ========================================================================
    // REPORTS
    // ========================================================================
    async generateReports() {
        console.log('\n' + '═'.repeat(70));
        console.log('📊 GENERATING REPORTS');
        console.log('═'.repeat(70));

        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        const ssStats = this.ss.getStats();

        console.log(`\n📸 Screenshots: ${ssStats.total} total in ${ssStats.categories} categories`);

        const fullReport = {
            meta: {
                timestamp: new Date().toISOString(),
                baseUrl: CONFIG.baseUrl,
                duration: `${Math.round((Date.now() - this.startTime) / 1000)}s`,
                version: 'V2'
            },
            results: this.results,
            screenshots: ssStats
        };

        const jsonPath = path.join(CONFIG.reportDir, `ultra-comprehensive-v2-${timestamp}.json`);
        fs.writeFileSync(jsonPath, JSON.stringify(fullReport, null, 2));
        console.log(`✅ JSON Report: ${jsonPath}`);

        const mdReport = this.generateMarkdownReport(fullReport);
        const mdPath = path.join(CONFIG.reportDir, `ultra-comprehensive-v2-${timestamp}.md`);
        fs.writeFileSync(mdPath, mdReport);
        console.log(`✅ Markdown Report: ${mdPath}`);

        const indexPath = path.join(CONFIG.screenshotDir, 'INDEX.md');
        fs.writeFileSync(indexPath, this.generateScreenshotIndex());
        console.log(`✅ Screenshot Index: ${indexPath}`);

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

        // Print category breakdown
        console.log('📁 Screenshots by Category:');
        const sorted = Object.entries(ssStats.byCategory).sort((a, b) => b[1] - a[1]);
        for (const [cat, count] of sorted) {
            console.log(`   ${cat}: ${count}`);
        }
    }

    generateMarkdownReport(report) {
        let md = `# Ultra-Comprehensive Test Report V2\n\n`;
        md += `**Generated:** ${report.meta.timestamp}\n`;
        md += `**Duration:** ${report.meta.duration}\n`;
        md += `**Version:** ${report.meta.version}\n\n`;

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

        return md;
    }

    generateScreenshotIndex() {
        let md = `# Screenshot Index V2\n\n`;
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
const suite = new UltraComprehensiveTestSuiteV2();
suite.runAllTests().catch(console.error);
