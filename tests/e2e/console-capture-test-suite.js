/**
 * ============================================================================
 * ABLAGE-SYSTEM CONSOLE CAPTURE TEST SUITE
 * ============================================================================
 *
 * Erfasst ALLE Browser-Konsolen-Ausgaben bei jeder Aktion:
 * - console.error (Fehler)
 * - console.warn (Warnungen)
 * - console.log (Logs)
 * - console.info (Info)
 * - console.debug (Debug)
 * - console.trace (Traces)
 * - Uncaught Exceptions (pageerror)
 * - Failed Network Requests
 * - React/Framework Errors
 *
 * Speichert alles für spätere Analyse in strukturierten JSON/MD Dateien.
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
    outputDir: path.join(__dirname, '../../console-logs'),
    reportDir: path.join(__dirname, '../../test-reports'),
    timeout: {
        navigation: 30000,
        element: 10000,
        short: 1500,
        micro: 500
    },
    // Welche Log-Level erfassen?
    captureTypes: {
        error: true,      // console.error
        warning: true,    // console.warn  
        log: true,        // console.log
        info: true,       // console.info
        debug: true,      // console.debug
        trace: true,      // console.trace
        dir: true,        // console.dir
        table: true,      // console.table
        assert: true,     // console.assert failures
        count: true,      // console.count
        time: true,       // console.time/timeEnd
        clear: true       // console.clear
    },
    // Zusätzliche Erfassung
    captureNetworkErrors: true,
    capturePageErrors: true,     // Uncaught exceptions
    captureReactErrors: true,    // React boundary errors
    captureSourceMaps: true      // Stack traces mit Source Maps
};

// ============================================================================
// ALL ROUTES - 57+ pages
// ============================================================================
const ALL_ROUTES = {
    auth: [
        { path: '/login', name: 'login', public: true }
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
        { path: '/privat/finanzen', name: 'privat-finanzen' },
        { path: '/privat/notfall', name: 'privat-notfall' }
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
// CONSOLE LOG MANAGER
// ============================================================================
class ConsoleLogManager {
    constructor(baseDir) {
        this.baseDir = baseDir;
        this.logs = [];
        this.byPage = {};
        this.byType = {
            error: [],
            warning: [],
            log: [],
            info: [],
            debug: [],
            trace: [],
            other: [],
            pageerror: [],
            network: []
        };
        this.byAction = {};
        this.currentAction = null;
        this.actionCounter = 0;
        this.errorCount = 0;
        this.warningCount = 0;
        this.totalCount = 0;
    }

    startAction(actionName, page, context = {}) {
        this.actionCounter++;
        const actionId = `${String(this.actionCounter).padStart(4, '0')}_${actionName}`;
        
        this.currentAction = {
            id: actionId,
            name: actionName,
            page: page,
            context: context,
            startTime: new Date().toISOString(),
            logs: []
        };

        if (!this.byPage[page]) {
            this.byPage[page] = [];
        }
        if (!this.byAction[actionId]) {
            this.byAction[actionId] = [];
        }

        return actionId;
    }

    endAction() {
        if (this.currentAction) {
            this.currentAction.endTime = new Date().toISOString();
            this.currentAction = null;
        }
    }

    addLog(entry) {
        this.totalCount++;
        
        const logEntry = {
            id: this.totalCount,
            timestamp: new Date().toISOString(),
            action: this.currentAction?.id || 'unknown',
            actionName: this.currentAction?.name || 'unknown',
            page: this.currentAction?.page || 'unknown',
            ...entry
        };

        this.logs.push(logEntry);

        // Nach Typ sortieren
        const type = entry.type?.toLowerCase() || 'other';
        if (this.byType[type]) {
            this.byType[type].push(logEntry);
        } else {
            this.byType.other.push(logEntry);
        }

        // Nach Seite sortieren
        if (this.currentAction?.page) {
            if (!this.byPage[this.currentAction.page]) {
                this.byPage[this.currentAction.page] = [];
            }
            this.byPage[this.currentAction.page].push(logEntry);
        }

        // Nach Aktion sortieren
        if (this.currentAction?.id) {
            if (!this.byAction[this.currentAction.id]) {
                this.byAction[this.currentAction.id] = [];
            }
            this.byAction[this.currentAction.id].push(logEntry);
            this.currentAction.logs.push(logEntry);
        }

        // Zähler
        if (type === 'error' || type === 'pageerror') {
            this.errorCount++;
        } else if (type === 'warning') {
            this.warningCount++;
        }

        // Console Output
        const icon = this.getTypeIcon(type);
        const preview = (entry.text || entry.message || '').substring(0, 80);
        console.log(`    ${icon} [${type.toUpperCase()}] ${preview}`);

        return logEntry;
    }

    getTypeIcon(type) {
        const icons = {
            error: '❌',
            warning: '⚠️',
            log: '📝',
            info: 'ℹ️',
            debug: '🔧',
            trace: '📍',
            pageerror: '💥',
            network: '🌐',
            other: '📋'
        };
        return icons[type] || '📋';
    }

    getStats() {
        return {
            total: this.totalCount,
            errors: this.errorCount,
            warnings: this.warningCount,
            byType: Object.fromEntries(
                Object.entries(this.byType).map(([k, v]) => [k, v.length])
            ),
            pages: Object.keys(this.byPage).length,
            actions: Object.keys(this.byAction).length
        };
    }

    async saveAll() {
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        
        // Hauptverzeichnisse erstellen
        const dirs = [
            'by-page',
            'by-type',
            'by-action',
            'errors-only',
            'warnings-only',
            'analysis'
        ];
        
        for (const dir of dirs) {
            fs.mkdirSync(path.join(this.baseDir, dir), { recursive: true });
        }

        // Alle Logs als JSON
        const allLogsPath = path.join(this.baseDir, `all-console-logs-${timestamp}.json`);
        fs.writeFileSync(allLogsPath, JSON.stringify({
            meta: {
                timestamp: new Date().toISOString(),
                stats: this.getStats()
            },
            logs: this.logs
        }, null, 2));

        // Nach Seite
        for (const [page, logs] of Object.entries(this.byPage)) {
            const pagePath = path.join(this.baseDir, 'by-page', `${page}.json`);
            fs.writeFileSync(pagePath, JSON.stringify({
                page,
                count: logs.length,
                errors: logs.filter(l => l.type === 'error' || l.type === 'pageerror').length,
                warnings: logs.filter(l => l.type === 'warning').length,
                logs
            }, null, 2));
        }

        // Nach Typ
        for (const [type, logs] of Object.entries(this.byType)) {
            if (logs.length > 0) {
                const typePath = path.join(this.baseDir, 'by-type', `${type}.json`);
                fs.writeFileSync(typePath, JSON.stringify({
                    type,
                    count: logs.length,
                    logs
                }, null, 2));
            }
        }

        // Nur Errors
        const errorsPath = path.join(this.baseDir, 'errors-only', `errors-${timestamp}.json`);
        const allErrors = [...this.byType.error, ...this.byType.pageerror, ...this.byType.network.filter(n => n.isError)];
        fs.writeFileSync(errorsPath, JSON.stringify({
            count: allErrors.length,
            errors: allErrors
        }, null, 2));

        // Nur Warnings
        const warningsPath = path.join(this.baseDir, 'warnings-only', `warnings-${timestamp}.json`);
        fs.writeFileSync(warningsPath, JSON.stringify({
            count: this.byType.warning.length,
            warnings: this.byType.warning
        }, null, 2));

        // Analyse-Zusammenfassung
        const analysisPath = path.join(this.baseDir, 'analysis', `summary-${timestamp}.json`);
        fs.writeFileSync(analysisPath, JSON.stringify(this.generateAnalysis(), null, 2));

        // Markdown Report
        const mdPath = path.join(this.baseDir, 'analysis', `report-${timestamp}.md`);
        fs.writeFileSync(mdPath, this.generateMarkdownReport());

        // CSV für einfache Analyse
        const csvPath = path.join(this.baseDir, 'analysis', `logs-${timestamp}.csv`);
        fs.writeFileSync(csvPath, this.generateCSV());

        console.log(`\n📁 Logs gespeichert in: ${this.baseDir}`);
        console.log(`   - Alle Logs: ${allLogsPath}`);
        console.log(`   - Nach Seite: ${Object.keys(this.byPage).length} Dateien`);
        console.log(`   - Nach Typ: ${Object.keys(this.byType).filter(k => this.byType[k].length > 0).length} Dateien`);
        console.log(`   - Analyse: ${analysisPath}`);
    }

    generateAnalysis() {
        // Häufigste Fehler gruppieren
        const errorPatterns = {};
        const allErrors = [...this.byType.error, ...this.byType.pageerror];
        
        for (const error of allErrors) {
            const msg = (error.text || error.message || '').substring(0, 100);
            if (!errorPatterns[msg]) {
                errorPatterns[msg] = {
                    count: 0,
                    pages: new Set(),
                    firstSeen: error.timestamp,
                    lastSeen: error.timestamp,
                    examples: []
                };
            }
            errorPatterns[msg].count++;
            errorPatterns[msg].pages.add(error.page);
            errorPatterns[msg].lastSeen = error.timestamp;
            if (errorPatterns[msg].examples.length < 3) {
                errorPatterns[msg].examples.push(error);
            }
        }

        // Warning-Patterns
        const warningPatterns = {};
        for (const warning of this.byType.warning) {
            const msg = (warning.text || warning.message || '').substring(0, 100);
            if (!warningPatterns[msg]) {
                warningPatterns[msg] = {
                    count: 0,
                    pages: new Set(),
                    examples: []
                };
            }
            warningPatterns[msg].count++;
            warningPatterns[msg].pages.add(warning.page);
            if (warningPatterns[msg].examples.length < 3) {
                warningPatterns[msg].examples.push(warning);
            }
        }

        // Problematische Seiten identifizieren
        const pageHealth = {};
        for (const [page, logs] of Object.entries(this.byPage)) {
            const errors = logs.filter(l => l.type === 'error' || l.type === 'pageerror').length;
            const warnings = logs.filter(l => l.type === 'warning').length;
            pageHealth[page] = {
                total: logs.length,
                errors,
                warnings,
                healthScore: Math.max(0, 100 - (errors * 10) - (warnings * 2))
            };
        }

        return {
            stats: this.getStats(),
            errorPatterns: Object.fromEntries(
                Object.entries(errorPatterns)
                    .sort((a, b) => b[1].count - a[1].count)
                    .map(([k, v]) => [k, { ...v, pages: Array.from(v.pages) }])
            ),
            warningPatterns: Object.fromEntries(
                Object.entries(warningPatterns)
                    .sort((a, b) => b[1].count - a[1].count)
                    .slice(0, 20)
                    .map(([k, v]) => [k, { ...v, pages: Array.from(v.pages) }])
            ),
            pageHealth: Object.fromEntries(
                Object.entries(pageHealth).sort((a, b) => a[1].healthScore - b[1].healthScore)
            ),
            worstPages: Object.entries(pageHealth)
                .filter(([_, h]) => h.errors > 0)
                .sort((a, b) => b[1].errors - a[1].errors)
                .slice(0, 10)
                .map(([page, health]) => ({ page, ...health })),
            reactErrors: allErrors.filter(e => 
                (e.text || '').includes('React') || 
                (e.text || '').includes('component') ||
                (e.text || '').includes('hook')
            ),
            networkErrors: this.byType.network.filter(n => n.isError)
        };
    }

    generateMarkdownReport() {
        const stats = this.getStats();
        const analysis = this.generateAnalysis();

        let md = `# Console Log Analysis Report\n\n`;
        md += `**Generated:** ${new Date().toISOString()}\n\n`;

        md += `## Summary\n\n`;
        md += `| Metric | Count |\n|--------|-------|\n`;
        md += `| Total Logs | ${stats.total} |\n`;
        md += `| Errors | ${stats.errors} |\n`;
        md += `| Warnings | ${stats.warnings} |\n`;
        md += `| Pages Tested | ${stats.pages} |\n`;
        md += `| Actions Performed | ${stats.actions} |\n\n`;

        md += `## Log Types\n\n`;
        md += `| Type | Count |\n|------|-------|\n`;
        for (const [type, count] of Object.entries(stats.byType)) {
            if (count > 0) {
                md += `| ${type} | ${count} |\n`;
            }
        }
        md += `\n`;

        if (analysis.worstPages.length > 0) {
            md += `## Problematic Pages\n\n`;
            md += `| Page | Errors | Warnings | Health Score |\n|------|--------|----------|-------------|\n`;
            for (const page of analysis.worstPages) {
                md += `| ${page.page} | ${page.errors} | ${page.warnings} | ${page.healthScore}% |\n`;
            }
            md += `\n`;
        }

        const errorPatternsList = Object.entries(analysis.errorPatterns).slice(0, 10);
        if (errorPatternsList.length > 0) {
            md += `## Top Error Patterns\n\n`;
            for (const [pattern, data] of errorPatternsList) {
                md += `### ${data.count}x: \`${pattern}\`\n`;
                md += `- Pages: ${data.pages.join(', ')}\n`;
                md += `- First seen: ${data.firstSeen}\n\n`;
            }
        }

        const warningPatternsList = Object.entries(analysis.warningPatterns).slice(0, 10);
        if (warningPatternsList.length > 0) {
            md += `## Top Warning Patterns\n\n`;
            for (const [pattern, data] of warningPatternsList) {
                md += `- **${data.count}x**: \`${pattern}\` (${data.pages.length} pages)\n`;
            }
            md += `\n`;
        }

        if (analysis.reactErrors.length > 0) {
            md += `## React-Specific Errors\n\n`;
            for (const error of analysis.reactErrors.slice(0, 10)) {
                md += `- **${error.page}**: ${(error.text || '').substring(0, 150)}\n`;
            }
            md += `\n`;
        }

        if (analysis.networkErrors.length > 0) {
            md += `## Network Errors\n\n`;
            for (const error of analysis.networkErrors.slice(0, 10)) {
                md += `- **${error.page}**: ${error.url} (${error.status})\n`;
            }
            md += `\n`;
        }

        return md;
    }

    generateCSV() {
        let csv = 'id,timestamp,page,action,type,message,location,stack\n';
        
        for (const log of this.logs) {
            const msg = (log.text || log.message || '').replace(/"/g, '""').substring(0, 500);
            const loc = (log.location || '').replace(/"/g, '""');
            const stack = (log.stack || '').replace(/"/g, '""').replace(/\n/g, ' ').substring(0, 500);
            
            csv += `${log.id},"${log.timestamp}","${log.page}","${log.actionName}","${log.type}","${msg}","${loc}","${stack}"\n`;
        }

        return csv;
    }
}

// ============================================================================
// MAIN TEST SUITE
// ============================================================================
class ConsoleCaptureSuite {
    constructor() {
        this.browser = null;
        this.context = null;
        this.page = null;
        this.logger = null;
        this.results = { passed: 0, failed: 0, skipped: 0 };
        this.startTime = Date.now();
    }

    async init() {
        console.log('\n' + '═'.repeat(70));
        console.log('🔍 CONSOLE CAPTURE TEST SUITE');
        console.log('   - Alle console.error erfassen');
        console.log('   - Alle console.warn erfassen');
        console.log('   - Alle console.log/info/debug erfassen');
        console.log('   - Uncaught Exceptions erfassen');
        console.log('   - Network Errors erfassen');
        console.log('═'.repeat(70));
        console.log(`📁 Output: ${CONFIG.outputDir}`);
        console.log(`🌐 Base URL: ${CONFIG.baseUrl}`);
        console.log('═'.repeat(70) + '\n');

        // Verzeichnisse erstellen
        fs.mkdirSync(CONFIG.outputDir, { recursive: true });
        fs.mkdirSync(CONFIG.reportDir, { recursive: true });

        this.logger = new ConsoleLogManager(CONFIG.outputDir);

        // Browser starten
        this.browser = await chromium.launch({ 
            headless: true,
            devtools: false
        });

        this.context = await this.browser.newContext({
            viewport: { width: 1920, height: 1080 },
            locale: 'de-DE'
        });

        this.page = await this.context.newPage();

        // ============================================================
        // CONSOLE LISTENER - DAS HERZSTÜCK
        // ============================================================
        
        // Alle Console Messages erfassen
        this.page.on('console', async (msg) => {
            const type = msg.type();
            
            if (!CONFIG.captureTypes[type]) return;

            const location = msg.location();
            let text = msg.text();

            // Argumente auslesen für mehr Details
            let args = [];
            try {
                for (const arg of msg.args()) {
                    const val = await arg.jsonValue().catch(() => arg.toString());
                    args.push(val);
                }
            } catch (e) {}

            this.logger.addLog({
                type,
                text,
                args: args.length > 0 ? args : undefined,
                location: location ? `${location.url}:${location.lineNumber}:${location.columnNumber}` : undefined,
                url: location?.url,
                line: location?.lineNumber,
                column: location?.columnNumber
            });
        });

        // Uncaught Exceptions / Page Errors
        this.page.on('pageerror', (error) => {
            this.logger.addLog({
                type: 'pageerror',
                text: error.message,
                message: error.message,
                stack: error.stack,
                name: error.name
            });
        });

        // Request Failures
        this.page.on('requestfailed', (request) => {
            if (!CONFIG.captureNetworkErrors) return;
            
            const failure = request.failure();
            this.logger.addLog({
                type: 'network',
                isError: true,
                text: `Request failed: ${request.url()}`,
                url: request.url(),
                method: request.method(),
                errorText: failure?.errorText,
                resourceType: request.resourceType()
            });
        });

        // Response Errors (4xx, 5xx)
        this.page.on('response', (response) => {
            if (!CONFIG.captureNetworkErrors) return;
            
            const status = response.status();
            if (status >= 400) {
                this.logger.addLog({
                    type: 'network',
                    isError: status >= 500,
                    isWarning: status >= 400 && status < 500,
                    text: `HTTP ${status}: ${response.url()}`,
                    url: response.url(),
                    status,
                    statusText: response.statusText()
                });
            }
        });

        console.log('✅ Browser initialized with console listeners\n');
    }

    // ========================================================================
    // LOGIN
    // ========================================================================
    async login() {
        console.log('🔐 Logging in...');

        this.logger.startAction('login-navigate', 'login');
        await this.page.goto(`${CONFIG.baseUrl}/login`, { waitUntil: 'networkidle' });
        await this.page.waitForTimeout(1500);
        this.logger.endAction();

        this.logger.startAction('login-fill-credentials', 'login');
        await this.page.fill('#email', CONFIG.credentials.email);
        await this.page.fill('#password', CONFIG.credentials.password);
        this.logger.endAction();

        this.logger.startAction('login-submit', 'login');
        await this.page.click('button[type="submit"]');
        await this.page.waitForTimeout(3000);
        this.logger.endAction();

        const currentUrl = this.page.url();
        if (!currentUrl.includes('/login')) {
            console.log('✅ Login successful\n');
            return true;
        }

        console.log('❌ Login failed\n');
        return false;
    }

    // ========================================================================
    // TEST ALL BUTTONS
    // ========================================================================
    async testAllButtons(pageName) {
        const buttons = await this.page.$$('button:visible');
        console.log(`   🔘 Testing ${buttons.length} buttons...`);

        const safePatterns = ['Neu', 'Erstellen', 'Add', 'New', 'Create', 'Filter', 'Suchen', 'Aktualisieren', 'Refresh'];
        const dangerPatterns = ['Löschen', 'Delete', 'Entfernen', 'Remove'];

        let btnIndex = 0;
        for (const btn of buttons.slice(0, 30)) {
            btnIndex++;
            try {
                const text = ((await btn.textContent()) || '').trim().substring(0, 25);
                const isDisabled = await btn.isDisabled();

                // Hover
                this.logger.startAction(`button-${btnIndex}-hover-${text}`, pageName, { button: text });
                await btn.scrollIntoViewIfNeeded();
                await btn.hover();
                await this.page.waitForTimeout(200);
                this.logger.endAction();

                // Click sichere Buttons
                const isSafe = safePatterns.some(p => text.toLowerCase().includes(p.toLowerCase()));
                const isDanger = dangerPatterns.some(p => text.toLowerCase().includes(p.toLowerCase()));

                if (isSafe && !isDanger && !isDisabled) {
                    this.logger.startAction(`button-${btnIndex}-click-${text}`, pageName, { button: text });
                    await btn.click();
                    await this.page.waitForTimeout(500);
                    this.logger.endAction();

                    // Modal schließen falls geöffnet
                    const modal = await this.page.$('[role="dialog"]:visible');
                    if (modal) {
                        this.logger.startAction(`button-${btnIndex}-close-modal`, pageName);
                        await this.page.keyboard.press('Escape');
                        await this.page.waitForTimeout(300);
                        this.logger.endAction();
                    }
                }

                // Danger buttons - Bestätigungsdialog testen
                if (isDanger && !isDisabled) {
                    this.logger.startAction(`button-${btnIndex}-danger-click-${text}`, pageName, { button: text, dangerous: true });
                    await btn.click();
                    await this.page.waitForTimeout(300);
                    
                    const confirmDialog = await this.page.$('[role="alertdialog"], [role="dialog"]:has-text("Löschen")');
                    if (confirmDialog) {
                        const cancelBtn = await this.page.$('button:has-text("Abbrechen"), button:has-text("Nein")');
                        if (cancelBtn) {
                            await cancelBtn.click();
                            await this.page.waitForTimeout(200);
                        } else {
                            await this.page.keyboard.press('Escape');
                            await this.page.waitForTimeout(200);
                        }
                    }
                    this.logger.endAction();
                }

            } catch (e) {
                this.logger.addLog({
                    type: 'error',
                    text: `Button test failed: ${e.message}`,
                    stack: e.stack
                });
            }
        }
    }

    // ========================================================================
    // TEST ALL FORMS
    // ========================================================================
    async testAllForms(pageName) {
        const forms = await this.page.$$('form:visible');
        console.log(`   📝 Testing ${forms.length} forms...`);

        let formIndex = 0;
        for (const form of forms) {
            formIndex++;
            try {
                await form.scrollIntoViewIfNeeded();

                // Leeres Submit testen (Validation triggern)
                const submitBtn = await form.$('button[type="submit"]');
                if (submitBtn && !await submitBtn.isDisabled()) {
                    this.logger.startAction(`form-${formIndex}-submit-empty`, pageName);
                    await submitBtn.click();
                    await this.page.waitForTimeout(300);
                    this.logger.endAction();
                }

                // Inputs ausfüllen
                const inputs = await form.$$('input:visible, textarea:visible, select:visible');
                for (const input of inputs) {
                    try {
                        const type = await input.getAttribute('type');
                        const name = await input.getAttribute('name') || '';
                        const isDisabled = await input.isDisabled();
                        if (isDisabled) continue;

                        this.logger.startAction(`form-${formIndex}-fill-${name || type}`, pageName);

                        if (type === 'email') await input.fill('test@example.com');
                        else if (type === 'password') await input.fill('Test123!');
                        else if (type === 'date') await input.fill('2025-12-31');
                        else if (type === 'number') await input.fill('100');
                        else if (type === 'tel') await input.fill('+49 123 456789');
                        else if (name.includes('iban')) await input.fill('DE89370400440532013000');
                        else if (type !== 'checkbox' && type !== 'radio') await input.fill('Test Eingabe');
                        
                        await input.blur();
                        await this.page.waitForTimeout(100);
                        this.logger.endAction();
                    } catch (e) {}
                }

                // Ausgefüllt submitten
                if (submitBtn && !await submitBtn.isDisabled()) {
                    this.logger.startAction(`form-${formIndex}-submit-filled`, pageName);
                    await submitBtn.click();
                    await this.page.waitForTimeout(500);
                    this.logger.endAction();
                }

            } catch (e) {}
        }
    }

    // ========================================================================
    // TEST ALL TABS
    // ========================================================================
    async testAllTabs(pageName) {
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

                    this.logger.startAction(`tab-${tabGroupIndex}-${i + 1}-${tabText}`, pageName);
                    await tab.click();
                    await this.page.waitForTimeout(300);
                    this.logger.endAction();
                }
            } catch (e) {}
        }
    }

    // ========================================================================
    // TEST ALL DROPDOWNS
    // ========================================================================
    async testAllDropdowns(pageName) {
        const dropdownTriggers = await this.page.$$('[aria-haspopup="true"], [aria-haspopup="listbox"], [aria-haspopup="menu"]');
        console.log(`   📋 Testing ${dropdownTriggers.length} dropdowns...`);

        let ddIndex = 0;
        for (const trigger of dropdownTriggers.slice(0, 15)) {
            ddIndex++;
            try {
                await trigger.scrollIntoViewIfNeeded();

                this.logger.startAction(`dropdown-${ddIndex}-open`, pageName);
                await trigger.click();
                await this.page.waitForTimeout(300);
                this.logger.endAction();

                // Option klicken
                const options = await this.page.$$('[role="option"]:visible, [role="menuitem"]:visible');
                if (options.length > 0) {
                    this.logger.startAction(`dropdown-${ddIndex}-select-option`, pageName);
                    await options[0].click();
                    await this.page.waitForTimeout(200);
                    this.logger.endAction();
                } else {
                    await this.page.keyboard.press('Escape');
                    await this.page.waitForTimeout(200);
                }

            } catch (e) {}
        }
    }

    // ========================================================================
    // TEST ALL TABLES
    // ========================================================================
    async testAllTables(pageName) {
        const tables = await this.page.$$('table:visible, [role="grid"]:visible');
        console.log(`   📊 Testing ${tables.length} tables...`);

        let tableIndex = 0;
        for (const table of tables) {
            tableIndex++;
            try {
                await table.scrollIntoViewIfNeeded();

                // Sorting testen
                const sortHeaders = await table.$$('th[aria-sort], th button, [role="columnheader"] button');
                for (let i = 0; i < Math.min(sortHeaders.length, 3); i++) {
                    this.logger.startAction(`table-${tableIndex}-sort-column-${i + 1}`, pageName);
                    await sortHeaders[i].click();
                    await this.page.waitForTimeout(300);
                    this.logger.endAction();
                }

                // Row actions testen
                const rows = await table.$$('tbody tr, [role="row"]');
                for (let i = 0; i < Math.min(rows.length, 3); i++) {
                    const row = rows[i];
                    const actions = await row.$$('button');
                    
                    for (let j = 0; j < Math.min(actions.length, 2); j++) {
                        const actionText = await actions[j].textContent();
                        if (!(actionText || '').toLowerCase().includes('löschen')) {
                            this.logger.startAction(`table-${tableIndex}-row-${i + 1}-action-${j + 1}`, pageName);
                            await actions[j].click();
                            await this.page.waitForTimeout(300);
                            
                            // Modal schließen
                            const modal = await this.page.$('[role="dialog"]:visible');
                            if (modal) {
                                await this.page.keyboard.press('Escape');
                                await this.page.waitForTimeout(200);
                            }
                            this.logger.endAction();
                        }
                    }
                }

            } catch (e) {}
        }
    }

    // ========================================================================
    // TEST SCROLLING
    // ========================================================================
    async testScrolling(pageName) {
        this.logger.startAction('scroll-to-bottom', pageName);
        await this.page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
        await this.page.waitForTimeout(500);
        this.logger.endAction();

        this.logger.startAction('scroll-to-top', pageName);
        await this.page.evaluate(() => window.scrollTo(0, 0));
        await this.page.waitForTimeout(300);
        this.logger.endAction();
    }

    // ========================================================================
    // TEST SINGLE PAGE - COMPLETE
    // ========================================================================
    async testPageComplete(route) {
        const { path: routePath, name } = route;

        console.log(`\n${'─'.repeat(60)}`);
        console.log(`📄 ${name.toUpperCase()} (${routePath})`);
        console.log('─'.repeat(60));

        try {
            // Navigation
            this.logger.startAction('navigate', name, { url: routePath });
            await this.page.goto(`${CONFIG.baseUrl}${routePath}`, {
                waitUntil: 'networkidle',
                timeout: CONFIG.timeout.navigation
            });
            await this.page.waitForTimeout(CONFIG.timeout.short);
            this.logger.endAction();

            // Initial state capture
            this.logger.startAction('initial-load', name);
            await this.page.waitForTimeout(500);
            this.logger.endAction();

            // Alle Elemente testen
            await this.testScrolling(name);
            await this.testAllButtons(name);
            await this.testAllForms(name);
            await this.testAllTabs(name);
            await this.testAllDropdowns(name);
            await this.testAllTables(name);

            // Hover über wichtige Elemente
            this.logger.startAction('hover-elements', name);
            const hoverables = await this.page.$$('[title], [data-tooltip], .tooltip-trigger');
            for (const el of hoverables.slice(0, 10)) {
                try {
                    await el.hover();
                    await this.page.waitForTimeout(200);
                } catch (e) {}
            }
            this.logger.endAction();

            // Final state
            this.logger.startAction('final-state', name);
            await this.page.waitForTimeout(300);
            this.logger.endAction();

            this.results.passed++;
            console.log(`   ✅ PASS`);
            return true;

        } catch (error) {
            console.log(`   ❌ FAIL - ${error.message}`);
            this.logger.addLog({
                type: 'error',
                text: `Page test failed: ${error.message}`,
                stack: error.stack
            });
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

            for (const route of routes) {
                await this.testPageComplete(route);
            }
        }

        await this.generateFinalReport();
        await this.cleanup();
    }

    // ========================================================================
    // REPORTS
    // ========================================================================
    async generateFinalReport() {
        console.log('\n' + '═'.repeat(70));
        console.log('📊 GENERATING REPORTS');
        console.log('═'.repeat(70));

        await this.logger.saveAll();

        const stats = this.logger.getStats();

        console.log('\n' + '═'.repeat(70));
        console.log('📈 FINAL SUMMARY');
        console.log('═'.repeat(70));
        console.log(`   Pages Tested: ${this.results.passed + this.results.failed}`);
        console.log(`   ✅ Passed: ${this.results.passed}`);
        console.log(`   ❌ Failed: ${this.results.failed}`);
        console.log(`   📋 Total Console Logs: ${stats.total}`);
        console.log(`   ❌ Errors: ${stats.errors}`);
        console.log(`   ⚠️ Warnings: ${stats.warnings}`);
        console.log(`   🕐 Duration: ${Math.round((Date.now() - this.startTime) / 1000)}s`);
        console.log('═'.repeat(70));

        console.log('\n📋 Logs by Type:');
        for (const [type, count] of Object.entries(stats.byType)) {
            if (count > 0) {
                console.log(`   ${this.logger.getTypeIcon(type)} ${type}: ${count}`);
            }
        }
        console.log('\n');
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
const suite = new ConsoleCaptureSuite();
suite.runAllTests().catch(console.error);
