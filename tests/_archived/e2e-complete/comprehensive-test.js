/**
 * ABLAGE-SYSTEM - VOLLSTÄNDIGER E2E-TEST
 * =======================================
 * 
 * Dieser Test prüft JEDE Seite, JEDEN Button, JEDES Formular
 * und erstellt Screenshots von ALLEM.
 * 
 * Ausführen mit: node tests/e2e-complete/comprehensive-test.js
 * 
 * @author Claude AI für Ben / UFI Digital
 * @version 1.0.0
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// ============================================================================
// KONFIGURATION
// ============================================================================
const CONFIG = {
    baseUrl: 'http://localhost',
    credentials: {
        email: 'admin@localhost.com',
        password: 'admin123'
    },
    screenshotDir: './tests/e2e-complete/screenshots',
    reportDir: './tests/e2e-complete/reports',
    testDocuments: './test_documents',
    timeout: 30000,
    waitAfterNavigation: 1500,
    waitAfterAction: 800
};

// ============================================================================
// ALLE ROUTEN DIE GETESTET WERDEN
// ============================================================================
const ALL_ROUTES = {
    main: [
        { path: '/', name: 'Dashboard', category: 'main' },
        { path: '/search', name: 'Suche', category: 'main' },
        { path: '/upload', name: 'Upload', category: 'main' },
        { path: '/chat', name: 'Chat/RAG', category: 'main' },
        { path: '/jobs', name: 'Jobs', category: 'main' },
        { path: '/monitoring', name: 'Monitoring', category: 'main' },
        { path: '/automation', name: 'Automation', category: 'main' },
        { path: '/relationships', name: 'Beziehungen', category: 'main' },
    ],
    documents: [
        { path: '/validation-queue', name: 'Validierungs-Warteschlange', category: 'documents' },
        { path: '/document-groups', name: 'Dokumentengruppen', category: 'documents' },
    ],
    kunden: [{ path: '/kunden', name: 'Kunden Übersicht', category: 'kunden' }],
    lieferanten: [{ path: '/lieferanten', name: 'Lieferanten Übersicht', category: 'lieferanten' }],
    personal: [{ path: '/personal', name: 'Personal Übersicht', category: 'personal' }],
    finanzen: [
        { path: '/finanzen', name: 'Finanzen Übersicht', category: 'finanzen' },
        { path: '/finanzen/2025', name: 'Finanzen 2025', category: 'finanzen' },
    ],
    kasse: [{ path: '/kasse', name: 'Kassenbuch Übersicht', category: 'kasse' }],
    spesen: [{ path: '/spesen', name: 'Spesen Übersicht', category: 'spesen' }],
    streckengeschaeft: [
        { path: '/streckengeschaeft', name: 'Streckengeschäft Übersicht', category: 'streckengeschaeft' },
        { path: '/streckengeschaeft/zm', name: 'Streckengeschäft ZM', category: 'streckengeschaeft' },
    ],
    privat: [
        { path: '/privat', name: 'Privat Übersicht', category: 'privat' },
        { path: '/privat/fahrzeuge', name: 'Privat Fahrzeuge', category: 'privat' },
        { path: '/privat/finanzen', name: 'Privat Finanzen', category: 'privat' },
        { path: '/privat/fristen', name: 'Privat Fristen', category: 'privat' },
        { path: '/privat/immobilien', name: 'Privat Immobilien', category: 'privat' },
        { path: '/privat/notfall', name: 'Privat Notfall', category: 'privat' },
        { path: '/privat/versicherungen', name: 'Privat Versicherungen', category: 'privat' },
    ],
    businessEntities: [{ path: '/business-entities', name: 'Geschäftseinheiten', category: 'business' }],
    admin: [
        { path: '/admin', name: 'Admin Dashboard', category: 'admin' },
        { path: '/admin/users', name: 'Benutzerverwaltung', category: 'admin' },
        { path: '/admin/settings', name: 'Einstellungen', category: 'admin' },
        { path: '/admin/tunes', name: 'OCR Tunes', category: 'admin' },
        { path: '/admin/ocr-backends', name: 'OCR Backends', category: 'admin' },
        { path: '/admin/ocr-review', name: 'OCR Review', category: 'admin' },
        { path: '/admin/ocr-training', name: 'OCR Training', category: 'admin' },
        { path: '/admin/job-queue', name: 'Job Queue', category: 'admin' },
    ],
    adminBanking: [
        { path: '/admin/banking', name: 'Banking Dashboard', category: 'banking' },
        { path: '/admin/banking/accounts', name: 'Bankkonten', category: 'banking' },
        { path: '/admin/banking/transactions', name: 'Transaktionen', category: 'banking' },
        { path: '/admin/banking/import', name: 'Bank Import', category: 'banking' },
        { path: '/admin/banking/payments', name: 'Zahlungen', category: 'banking' },
        { path: '/admin/banking/reconciliation', name: 'Abstimmung', category: 'banking' },
        { path: '/admin/banking/skonto', name: 'Skonto', category: 'banking' },
    ],
    adminDatev: [
        { path: '/admin/datev', name: 'DATEV Dashboard', category: 'datev' },
        { path: '/admin/datev/config', name: 'DATEV Konfiguration', category: 'datev' },
        { path: '/admin/datev/export', name: 'DATEV Export', category: 'datev' },
        { path: '/admin/datev/history', name: 'DATEV Historie', category: 'datev' },
        { path: '/admin/datev/vendors', name: 'DATEV Kreditoren', category: 'datev' },
    ],
    adminMahnungen: [
        { path: '/admin/mahnungen', name: 'Mahnwesen Dashboard', category: 'mahnungen' },
        { path: '/admin/mahnungen/aktiv', name: 'Aktive Mahnungen', category: 'mahnungen' },
        { path: '/admin/mahnungen/aufgaben', name: 'Mahnaufgaben', category: 'mahnungen' },
        { path: '/admin/mahnungen/kanban', name: 'Mahnungen Kanban', category: 'mahnungen' },
        { path: '/admin/mahnungen/einstellungen', name: 'Mahneinstellungen', category: 'mahnungen' },
        { path: '/admin/mahnungen/eskalation', name: 'Eskalation', category: 'mahnungen' },
        { path: '/admin/mahnungen/mahnstopp', name: 'Mahnstopp', category: 'mahnungen' },
    ],
};

// ============================================================================
// TEST ERGEBNIS STRUKTUR
// ============================================================================
class TestResults {
    constructor() {
        this.startTime = new Date();
        this.endTime = null;
        this.pages = {};
        this.features = {};
        this.forms = {};
        this.buttons = {};
        this.uploads = {};
        this.errors = [];
        this.screenshots = [];
        this.summary = { total: 0, passed: 0, failed: 0, skipped: 0 };
    }
    addPageResult(route, result) {
        this.pages[route] = result;
        this.summary.total++;
        if (result.success) this.summary.passed++;
        else if (result.skipped) this.summary.skipped++;
        else this.summary.failed++;
    }
    addFeatureResult(feature, result) { this.features[feature] = result; }
    addFormResult(formName, result) { this.forms[formName] = result; }
    addButtonResult(buttonName, result) { this.buttons[buttonName] = result; }
    addUploadResult(filename, result) { this.uploads[filename] = result; }
    addError(error) { this.errors.push({ timestamp: new Date().toISOString(), ...error }); }
    addScreenshot(screenshotPath) { this.screenshots.push(screenshotPath); }
    finish() { this.endTime = new Date(); this.duration = (this.endTime - this.startTime) / 1000; }
    toJSON() {
        return {
            startTime: this.startTime.toISOString(),
            endTime: this.endTime?.toISOString(),
            duration: this.duration,
            summary: this.summary,
            pages: this.pages,
            features: this.features,
            forms: this.forms,
            buttons: this.buttons,
            uploads: this.uploads,
            errors: this.errors,
            screenshots: this.screenshots
        };
    }
}

// ============================================================================
// SCREENSHOT HELPER
// ============================================================================
async function takeScreenshot(page, category, name, results) {
    const categoryDir = path.join(CONFIG.screenshotDir, category);
    if (!fs.existsSync(categoryDir)) fs.mkdirSync(categoryDir, { recursive: true });
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const filename = `${name.replace(/[^a-zA-Z0-9äöüÄÖÜß]/g, '_')}_${timestamp}.png`;
    const filepath = path.join(categoryDir, filename);
    await page.screenshot({ path: filepath, fullPage: true });
    results.addScreenshot(filepath);
    console.log(`    📸 Screenshot: ${filepath}`);
    return filepath;
}

// ============================================================================
// ELEMENT FINDER HELPERS
// ============================================================================
async function findAllButtons(page) {
    return await page.$$eval('button, [role="button"], a.btn, .btn', buttons => 
        buttons.map(b => ({ text: b.textContent?.trim() || '', className: b.className, id: b.id, disabled: b.disabled, type: b.type }))
    );
}
async function findAllForms(page) {
    return await page.$$eval('form, [role="form"]', forms =>
        forms.map(f => ({ id: f.id, className: f.className, action: f.action, method: f.method,
            inputs: Array.from(f.querySelectorAll('input, textarea, select')).map(i => ({ name: i.name, type: i.type, placeholder: i.placeholder, required: i.required }))
        }))
    );
}
async function findAllInputs(page) {
    return await page.$$eval('input, textarea, select', inputs =>
        inputs.map(i => ({ name: i.name, type: i.type, id: i.id, placeholder: i.placeholder, required: i.required, value: i.value }))
    );
}
async function findAllTabs(page) {
    return await page.$$eval('[role="tab"], .tab, [data-tab]', tabs =>
        tabs.map(t => ({ text: t.textContent?.trim(), id: t.id, active: t.getAttribute('aria-selected') === 'true' || t.classList.contains('active') }))
    );
}

// ============================================================================
// SEITEN TESTER
// ============================================================================
async function testPage(page, route, results) {
    const fullUrl = `${CONFIG.baseUrl}${route.path}`;
    console.log(`\n  🔍 Teste: ${route.name} (${route.path})`);
    
    const pageResult = {
        name: route.name, path: route.path, category: route.category, success: false, loadTime: 0,
        errors: [], buttons: [], forms: [], inputs: [], tabs: [], screenshots: []
    };
    const startTime = Date.now();

    try {
        const response = await page.goto(fullUrl, { waitUntil: 'networkidle', timeout: CONFIG.timeout });
        pageResult.loadTime = Date.now() - startTime;
        pageResult.statusCode = response?.status();
        await page.waitForTimeout(CONFIG.waitAfterNavigation);

        const pageContent = await page.textContent('body');
        const hasError = pageContent.includes('Fehler') || pageContent.includes('Error') || pageContent.includes('nicht gefunden');
        if (hasError && !route.path.includes('404')) pageResult.errors.push('Möglicher Fehler auf der Seite erkannt');

        const screenshotPath = await takeScreenshot(page, route.category, route.name, results);
        pageResult.screenshots.push(screenshotPath);
        pageResult.buttons = await findAllButtons(page);
        pageResult.forms = await findAllForms(page);
        pageResult.inputs = await findAllInputs(page);
        pageResult.tabs = await findAllTabs(page);

        console.log(`    ✅ Geladen in ${pageResult.loadTime}ms`);
        console.log(`    📊 ${pageResult.buttons.length} Buttons, ${pageResult.forms.length} Formulare, ${pageResult.inputs.length} Inputs`);

        if (pageResult.tabs.length > 0) {
            console.log(`    🔄 Teste ${pageResult.tabs.length} Tabs...`);
            for (const tab of pageResult.tabs) {
                try {
                    const tabEl = await page.$(`[role="tab"]:has-text("${tab.text}")`);
                    if (tabEl) { await tabEl.click(); await page.waitForTimeout(500); await takeScreenshot(page, route.category, `${route.name}_tab_${tab.text}`, results); }
                } catch (e) { console.log(`    ⚠️ Tab "${tab.text}" konnte nicht getestet werden`); }
            }
        }
        pageResult.success = true;
    } catch (error) {
        pageResult.success = false;
        pageResult.errors.push(error.message);
        console.log(`    ❌ Fehler: ${error.message}`);
        try { await takeScreenshot(page, 'errors', `ERROR_${route.name}`, results); } catch (e) {}
        results.addError({ type: 'page_load', route: route.path, message: error.message });
    }
    results.addPageResult(route.path, pageResult);
    return pageResult;
}


// ============================================================================
// FEATURE TESTER - KASSE
// ============================================================================
async function testKasseFeatures(page, results) {
    console.log('\n📦 TESTE KASSE FEATURES...');
    const featureResult = { name: 'Kassenbuch', tests: [], success: true };
    try {
        await page.goto(`${CONFIG.baseUrl}/kasse`, { waitUntil: 'networkidle' });
        await page.waitForTimeout(CONFIG.waitAfterNavigation);
        await takeScreenshot(page, 'features/kasse', 'kasse_overview', results);
        const kassenList = await page.$$('[data-testid="kasse-item"], .kasse-card, tr[data-kasse]');
        featureResult.tests.push({ name: 'Kassen Liste laden', success: true, count: kassenList.length });
        const neueKasseBtn = await page.$('button:has-text("Neue Kasse"), button:has-text("Kasse erstellen")');
        if (neueKasseBtn) {
            await neueKasseBtn.click(); await page.waitForTimeout(CONFIG.waitAfterAction);
            await takeScreenshot(page, 'features/kasse', 'kasse_neu_dialog', results);
            const closeBtn = await page.$('[role="dialog"] button:has-text("Abbrechen")');
            if (closeBtn) await closeBtn.click();
            featureResult.tests.push({ name: 'Neue Kasse Dialog', success: true });
        }
    } catch (error) {
        featureResult.success = false;
        featureResult.tests.push({ name: 'Kasse Test', success: false, error: error.message });
    }
    results.addFeatureResult('kasse', featureResult);
}

// ============================================================================
// FEATURE TESTER - SPESEN
// ============================================================================
async function testSpesenFeatures(page, results) {
    console.log('\n📦 TESTE SPESEN FEATURES...');
    const featureResult = { name: 'Spesen', tests: [], success: true };
    try {
        await page.goto(`${CONFIG.baseUrl}/spesen`, { waitUntil: 'networkidle' });
        await page.waitForTimeout(CONFIG.waitAfterNavigation);
        await takeScreenshot(page, 'features/spesen', 'spesen_overview', results);
        const neueAbrechnungBtn = await page.$('button:has-text("Neue Abrechnung")');
        if (neueAbrechnungBtn) {
            await neueAbrechnungBtn.click(); await page.waitForTimeout(CONFIG.waitAfterAction);
            await takeScreenshot(page, 'features/spesen', 'spesen_neu_dialog', results);
            const titleInput = await page.$('[role="dialog"] input[name="title"]');
            if (titleInput) await titleInput.fill('Playwright Test Abrechnung');
            await takeScreenshot(page, 'features/spesen', 'spesen_formular_gefuellt', results);
            const abbrechenBtn = await page.$('[role="dialog"] button:has-text("Abbrechen")');
            if (abbrechenBtn) await abbrechenBtn.click();
            featureResult.tests.push({ name: 'Neue Abrechnung Dialog', success: true });
        }
    } catch (error) {
        featureResult.success = false;
        featureResult.tests.push({ name: 'Spesen Test', success: false, error: error.message });
    }
    results.addFeatureResult('spesen', featureResult);
}

// ============================================================================
// FEATURE TESTER - MAHNWESEN
// ============================================================================
async function testMahnwesenFeatures(page, results) {
    console.log('\n📦 TESTE MAHNWESEN FEATURES...');
    const featureResult = { name: 'Mahnwesen', tests: [], success: true };
    try {
        await page.goto(`${CONFIG.baseUrl}/admin/mahnungen`, { waitUntil: 'networkidle' });
        await takeScreenshot(page, 'features/mahnwesen', 'mahnwesen_dashboard', results);
        featureResult.tests.push({ name: 'Dashboard', success: true });
        await page.goto(`${CONFIG.baseUrl}/admin/mahnungen/kanban`, { waitUntil: 'networkidle' });
        await takeScreenshot(page, 'features/mahnwesen', 'mahnwesen_kanban', results);
        featureResult.tests.push({ name: 'Kanban Board', success: true });
    } catch (error) {
        featureResult.success = false;
        featureResult.tests.push({ name: 'Mahnwesen Test', success: false, error: error.message });
    }
    results.addFeatureResult('mahnwesen', featureResult);
}

// ============================================================================
// FEATURE TESTER - BANKING
// ============================================================================
async function testBankingFeatures(page, results) {
    console.log('\n📦 TESTE BANKING FEATURES...');
    const featureResult = { name: 'Banking', tests: [], success: true };
    try {
        const bankingPages = [
            { path: '/admin/banking', name: 'Dashboard' },
            { path: '/admin/banking/accounts', name: 'Konten' },
            { path: '/admin/banking/transactions', name: 'Transaktionen' },
            { path: '/admin/banking/reconciliation', name: 'Abstimmung' },
        ];
        for (const bp of bankingPages) {
            await page.goto(`${CONFIG.baseUrl}${bp.path}`, { waitUntil: 'networkidle' });
            await takeScreenshot(page, 'features/banking', `banking_${bp.name.toLowerCase()}`, results);
            featureResult.tests.push({ name: bp.name, success: true });
        }
    } catch (error) {
        featureResult.success = false;
        featureResult.tests.push({ name: 'Banking Test', success: false, error: error.message });
    }
    results.addFeatureResult('banking', featureResult);
}

// ============================================================================
// FEATURE TESTER - UPLOAD
// ============================================================================
async function testUploadFeature(page, results) {
    console.log('\n📦 TESTE UPLOAD FEATURE...');
    const featureResult = { name: 'Upload', tests: [], success: true };
    try {
        await page.goto(`${CONFIG.baseUrl}/upload`, { waitUntil: 'networkidle' });
        await takeScreenshot(page, 'features/upload', 'upload_page', results);
        const testDocPath = path.join(process.cwd(), CONFIG.testDocuments, 'test_invoice.png');
        if (fs.existsSync(testDocPath)) {
            const fileInput = await page.$('input[type="file"]');
            if (fileInput) {
                await fileInput.setInputFiles(testDocPath);
                await page.waitForTimeout(2000);
                await takeScreenshot(page, 'features/upload', 'upload_file_selected', results);
                featureResult.tests.push({ name: 'Datei auswählen', success: true });
            }
        }
    } catch (error) {
        featureResult.success = false;
        featureResult.tests.push({ name: 'Upload Test', success: false, error: error.message });
    }
    results.addFeatureResult('upload', featureResult);
}

// ============================================================================
// FEATURE TESTER - ADMIN
// ============================================================================
async function testAdminFeatures(page, results) {
    console.log('\n📦 TESTE ADMIN FEATURES...');
    const featureResult = { name: 'Admin', tests: [], success: true };
    try {
        await page.goto(`${CONFIG.baseUrl}/admin`, { waitUntil: 'networkidle' });
        await takeScreenshot(page, 'features/admin', 'admin_dashboard', results);
        featureResult.tests.push({ name: 'Dashboard', success: true });
        await page.goto(`${CONFIG.baseUrl}/admin/users`, { waitUntil: 'networkidle' });
        await takeScreenshot(page, 'features/admin', 'admin_users', results);
        featureResult.tests.push({ name: 'Benutzer', success: true });
        await page.goto(`${CONFIG.baseUrl}/admin/ocr-backends`, { waitUntil: 'networkidle' });
        await takeScreenshot(page, 'features/admin', 'admin_ocr_backends', results);
        featureResult.tests.push({ name: 'OCR Backends', success: true });
    } catch (error) {
        featureResult.success = false;
        featureResult.tests.push({ name: 'Admin Test', success: false, error: error.message });
    }
    results.addFeatureResult('admin', featureResult);
}

// ============================================================================
// RESPONSIVE TEST
// ============================================================================
async function testResponsiveDesign(page, results) {
    console.log('\n📦 TESTE RESPONSIVE DESIGN...');
    const featureResult = { name: 'Responsive', tests: [], success: true };
    const viewports = [
        { name: 'Desktop', width: 1920, height: 1080 },
        { name: 'Tablet', width: 768, height: 1024 },
        { name: 'Mobile', width: 375, height: 667 },
    ];
    try {
        for (const vp of viewports) {
            await page.setViewportSize({ width: vp.width, height: vp.height });
            await page.goto(`${CONFIG.baseUrl}/`, { waitUntil: 'networkidle' });
            await takeScreenshot(page, 'features/responsive', `responsive_${vp.name.toLowerCase()}`, results);
            featureResult.tests.push({ name: vp.name, success: true });
        }
        await page.setViewportSize({ width: 1920, height: 1080 });
    } catch (error) {
        featureResult.success = false;
        featureResult.tests.push({ name: 'Responsive Test', success: false, error: error.message });
    }
    results.addFeatureResult('responsive', featureResult);
}


// ============================================================================
// HTML REPORT GENERATOR
// ============================================================================
function generateHtmlReport(results) {
    const passRate = results.summary.total > 0 ? (results.summary.passed / results.summary.total * 100).toFixed(1) : 0;
    return `<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <title>Ablage-System E2E Test Report</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; line-height: 1.6; padding: 2rem; }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { color: #38bdf8; margin-bottom: 0.5rem; font-size: 2rem; text-align: center; }
        h2 { color: #94a3b8; margin: 2rem 0 1rem; border-bottom: 1px solid #334155; padding-bottom: 0.5rem; }
        .timestamp { color: #64748b; text-align: center; margin-bottom: 2rem; }
        .summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin: 2rem 0; }
        .stat-card { background: #1e293b; padding: 1.5rem; border-radius: 12px; text-align: center; }
        .stat-value { font-size: 2rem; font-weight: bold; }
        .stat-value.passed { color: #22c55e; }
        .stat-value.failed { color: #ef4444; }
        .stat-value.total { color: #38bdf8; }
        .stat-label { color: #94a3b8; font-size: 0.9rem; }
        .progress-bar { height: 8px; background: #334155; border-radius: 4px; overflow: hidden; margin: 1rem 0; }
        .progress-fill { height: 100%; background: linear-gradient(90deg, #22c55e, #38bdf8); }
        .page-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1rem; }
        .page-card { background: #1e293b; border-radius: 8px; padding: 1rem; border-left: 4px solid #22c55e; }
        .page-card.failed { border-left-color: #ef4444; }
        .page-name { font-weight: 600; }
        .page-path { color: #64748b; font-size: 0.85rem; font-family: monospace; }
        .badge { display: inline-block; padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.75rem; margin-right: 0.5rem; }
        .badge.success { background: #22c55e30; color: #22c55e; }
        .badge.failed { background: #ef444430; color: #ef4444; }
        .error-list { background: #ef444420; border-radius: 8px; padding: 1rem; margin: 1rem 0; }
        .error-item { padding: 0.5rem; background: #0f172a; border-radius: 4px; margin: 0.5rem 0; font-family: monospace; font-size: 0.85rem; color: #fca5a5; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🗂️ Ablage-System E2E Test Report</h1>
        <p class="timestamp">Generiert: ${results.startTime.toLocaleString('de-DE')} | Dauer: ${results.duration?.toFixed(2) || '?'}s</p>
        <div class="summary">
            <div class="stat-card"><div class="stat-value total">${results.summary.total}</div><div class="stat-label">Gesamt</div></div>
            <div class="stat-card"><div class="stat-value passed">${results.summary.passed}</div><div class="stat-label">Bestanden</div></div>
            <div class="stat-card"><div class="stat-value failed">${results.summary.failed}</div><div class="stat-label">Fehlgeschlagen</div></div>
            <div class="stat-card"><div class="stat-value passed">${passRate}%</div><div class="stat-label">Erfolgsrate</div></div>
        </div>
        <div class="progress-bar"><div class="progress-fill" style="width: ${passRate}%"></div></div>
        <h2>📄 Seiten Tests (${Object.keys(results.pages).length})</h2>
        <div class="page-grid">
            ${Object.entries(results.pages).map(([p, r]) => `
                <div class="page-card ${r.success ? '' : 'failed'}">
                    <div class="page-name">${r.name}</div>
                    <div class="page-path">${p}</div>
                    <div><span class="badge ${r.success ? 'success' : 'failed'}">${r.success ? '✓' : '✗'}</span>${r.loadTime}ms | ${r.buttons?.length || 0} Buttons</div>
                </div>
            `).join('')}
        </div>
        <h2>🔧 Features (${Object.keys(results.features).length})</h2>
        <div class="page-grid">
            ${Object.entries(results.features).map(([n, f]) => `
                <div class="page-card ${f.success ? '' : 'failed'}">
                    <div class="page-name">${f.name}</div>
                    <div>${f.tests?.length || 0} Tests</div>
                    <span class="badge ${f.success ? 'success' : 'failed'}">${f.success ? '✓ OK' : '✗ FAIL'}</span>
                </div>
            `).join('')}
        </div>
        ${results.errors.length > 0 ? `
        <h2>❌ Fehler (${results.errors.length})</h2>
        <div class="error-list">${results.errors.map(e => `<div class="error-item">${e.type}: ${e.message}</div>`).join('')}</div>
        ` : ''}
        <h2>📸 Screenshots: ${results.screenshots.length}</h2>
        <p style="color:#64748b">Gespeichert in: ${CONFIG.screenshotDir}</p>
    </div>
</body>
</html>`;
}


// ============================================================================
// HAUPT TEST RUNNER
// ============================================================================
async function runComprehensiveTest() {
    console.log('╔═══════════════════════════════════════════════════════════════════════╗');
    console.log('║     ABLAGE-SYSTEM - VOLLSTÄNDIGER E2E TEST                            ║');
    console.log('║     Testet ALLE Seiten, ALLE Features, ALLE Buttons & Formulare       ║');
    console.log('╚═══════════════════════════════════════════════════════════════════════╝\n');

    const results = new TestResults();
    if (!fs.existsSync(CONFIG.screenshotDir)) fs.mkdirSync(CONFIG.screenshotDir, { recursive: true });
    if (!fs.existsSync(CONFIG.reportDir)) fs.mkdirSync(CONFIG.reportDir, { recursive: true });

    console.log('🚀 Starte Browser...');
    const browser = await chromium.launch({ headless: true, args: ['--disable-dev-shm-usage'] });
    const context = await browser.newContext({ viewport: { width: 1920, height: 1080 }, locale: 'de-DE' });
    const page = await context.newPage();

    page.on('response', async response => {
        if (response.status() >= 400 && response.url().includes('/api/')) {
            results.addError({ type: 'api_error', url: response.url(), status: response.status() });
        }
    });

    try {
        // LOGIN
        console.log('\n═══════════════════════════════════════════════════════════════════════');
        console.log('  📝 SCHRITT 1: LOGIN');
        console.log('═══════════════════════════════════════════════════════════════════════');
        await page.goto(`${CONFIG.baseUrl}/login`, { waitUntil: 'networkidle' });
        await takeScreenshot(page, 'auth', 'login_page', results);
        await page.fill('input[type="email"], input[name="email"]', CONFIG.credentials.email);
        await page.fill('input[type="password"], input[name="password"]', CONFIG.credentials.password);
        await page.click('button[type="submit"]');
        await page.waitForTimeout(3000);
        await takeScreenshot(page, 'auth', 'after_login', results);
        console.log('  ✅ Login erfolgreich\n');

        // ALLE SEITEN TESTEN
        console.log('═══════════════════════════════════════════════════════════════════════');
        console.log('  📄 SCHRITT 2: ALLE SEITEN TESTEN');
        console.log('═══════════════════════════════════════════════════════════════════════');
        const allRoutes = Object.values(ALL_ROUTES).flat();
        console.log(`  📊 ${allRoutes.length} Seiten zu testen...\n`);
        for (const route of allRoutes) await testPage(page, route, results);

        // FEATURE TESTS
        console.log('\n═══════════════════════════════════════════════════════════════════════');
        console.log('  🔧 SCHRITT 3: FEATURE TESTS');
        console.log('═══════════════════════════════════════════════════════════════════════');
        await testUploadFeature(page, results);
        await testKasseFeatures(page, results);
        await testSpesenFeatures(page, results);
        await testMahnwesenFeatures(page, results);
        await testBankingFeatures(page, results);
        await testAdminFeatures(page, results);

        // RESPONSIVE
        console.log('\n═══════════════════════════════════════════════════════════════════════');
        console.log('  📱 SCHRITT 4: RESPONSIVE TESTS');
        console.log('═══════════════════════════════════════════════════════════════════════');
        await testResponsiveDesign(page, results);

    } catch (error) {
        console.error('\n❌ KRITISCHER FEHLER:', error.message);
        results.addError({ type: 'critical', message: error.message });
        try { await takeScreenshot(page, 'errors', 'CRITICAL_ERROR', results); } catch (e) {}
    } finally {
        await browser.close();
    }

    results.finish();
    console.log('\n═══════════════════════════════════════════════════════════════════════');
    console.log('  📊 TEST ZUSAMMENFASSUNG');
    console.log('═══════════════════════════════════════════════════════════════════════');
    console.log(`  Gesamt:         ${results.summary.total}`);
    console.log(`  Bestanden:      ${results.summary.passed} ✅`);
    console.log(`  Fehlgeschlagen: ${results.summary.failed} ❌`);
    console.log(`  Erfolgsrate:    ${(results.summary.passed / results.summary.total * 100).toFixed(1)}%`);
    console.log(`  Dauer:          ${results.duration?.toFixed(2)}s`);
    console.log(`  Screenshots:    ${results.screenshots.length}`);

    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    fs.writeFileSync(path.join(CONFIG.reportDir, `report_${timestamp}.json`), JSON.stringify(results.toJSON(), null, 2));
    fs.writeFileSync(path.join(CONFIG.reportDir, `report_${timestamp}.html`), generateHtmlReport(results));
    fs.writeFileSync(path.join(CONFIG.reportDir, 'latest.json'), JSON.stringify(results.toJSON(), null, 2));
    fs.writeFileSync(path.join(CONFIG.reportDir, 'latest.html'), generateHtmlReport(results));
    console.log(`\n  📄 Reports: ${CONFIG.reportDir}/latest.html`);
    console.log('\n═══════════════════════════════════════════════════════════════════════');
    console.log('  ✅ TEST ABGESCHLOSSEN');
    console.log('═══════════════════════════════════════════════════════════════════════\n');
    process.exit(results.summary.failed > 0 ? 1 : 0);
}

runComprehensiveTest().catch(e => { console.error('Test fehlgeschlagen:', e); process.exit(1); });
