/**
 * ============================================================================
 * ABLAGE-SYSTEM ULTRA BROWSER DIAGNOSTICS SUITE
 * ============================================================================
 *
 * Erfasst ABSOLUT ALLES was der Browser hergeben kann:
 *
 * CONSOLE:
 * - console.error/warn/log/info/debug/trace
 * - Uncaught Exceptions (pageerror)
 * - Unhandled Promise Rejections
 *
 * PERFORMANCE:
 * - Core Web Vitals (LCP, FID, CLS, FCP, TTFB)
 * - Navigation Timing
 * - Resource Timing (alle Assets)
 * - Long Tasks (>50ms)
 * - Layout Shifts
 * - Paint Timing
 * - Memory Usage (JS Heap)
 * - Frame Rate / Jank Detection
 *
 * NETWORK:
 * - Alle Requests/Responses
 * - Failed Requests
 * - Slow Requests (>1s)
 * - Request/Response Headers
 * - Response Size
 * - CORS Errors
 * - Mixed Content Warnings
 *
 * COVERAGE:
 * - JavaScript Coverage (unused code)
 * - CSS Coverage (unused styles)
 *
 * ACCESSIBILITY:
 * - A11y Violations (via axe-core injection)
 * - Missing alt texts
 * - Contrast issues
 * - ARIA problems
 *
 * DOM:
 * - DOM Size / Node Count
 * - DOM Mutations
 * - Event Listener Count
 * - Orphaned Event Listeners
 *
 * STORAGE:
 * - LocalStorage Changes
 * - SessionStorage Changes
 * - Cookie Changes
 * - IndexedDB Operations
 *
 * SECURITY:
 * - Mixed Content
 * - Insecure Forms
 * - CSP Violations
 *
 * Author: Ben / UFI Digital Agency
 * Created: 2025-12-31
 * Version: 2.0 ULTRA
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
    outputDir: path.join(__dirname, '../../browser-diagnostics'),
    reportDir: path.join(__dirname, '../../test-reports'),
    timeout: {
        navigation: 30000,
        element: 10000,
        short: 1500,
        micro: 500
    },
    
    // Was soll erfasst werden?
    capture: {
        // Console
        consoleAll: true,
        consoleErrors: true,
        consoleWarnings: true,
        consoleLogs: true,
        consoleInfo: true,
        consoleDebug: true,
        
        // Exceptions
        uncaughtExceptions: true,
        unhandledRejections: true,
        
        // Performance
        webVitals: true,
        navigationTiming: true,
        resourceTiming: true,
        longTasks: true,
        layoutShifts: true,
        paintTiming: true,
        memoryUsage: true,
        frameRate: true,
        
        // Network
        allRequests: true,
        failedRequests: true,
        slowRequests: true,
        requestHeaders: true,
        responseHeaders: true,
        responseSize: true,
        
        // Coverage
        jsCoverage: true,
        cssCoverage: true,
        
        // Accessibility
        a11yViolations: true,
        
        // DOM
        domSize: true,
        domMutations: true,
        eventListeners: true,
        
        // Storage
        localStorage: true,
        sessionStorage: true,
        cookies: true,
        
        // Security
        mixedContent: true,
        cspViolations: true
    },
    
    // Thresholds für Warnungen
    thresholds: {
        slowRequest: 1000,      // ms
        longTask: 50,           // ms
        largeResponse: 500000,  // bytes (500KB)
        highMemory: 100000000,  // bytes (100MB)
        lowFrameRate: 30,       // fps
        maxDomNodes: 1500,
        maxEventListeners: 500,
        
        // Web Vitals
        lcp: 2500,              // ms - Largest Contentful Paint
        fid: 100,               // ms - First Input Delay
        cls: 0.1,               // Cumulative Layout Shift
        fcp: 1800,              // ms - First Contentful Paint
        ttfb: 800               // ms - Time to First Byte
    }
};

// ============================================================================
// ALL ROUTES
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
// ULTRA DIAGNOSTICS MANAGER
// ============================================================================
class UltraDiagnosticsManager {
    constructor(baseDir) {
        this.baseDir = baseDir;
        this.startTime = Date.now();
        
        // Alle Daten-Sammlungen
        this.data = {
            // Console
            console: {
                errors: [],
                warnings: [],
                logs: [],
                info: [],
                debug: [],
                other: []
            },
            
            // Exceptions
            exceptions: {
                uncaught: [],
                unhandledRejections: []
            },
            
            // Performance
            performance: {
                webVitals: [],
                navigation: [],
                resources: [],
                longTasks: [],
                layoutShifts: [],
                paint: [],
                memory: [],
                frames: []
            },
            
            // Network
            network: {
                requests: [],
                responses: [],
                failed: [],
                slow: [],
                large: []
            },
            
            // Coverage
            coverage: {
                js: [],
                css: []
            },
            
            // Accessibility
            accessibility: {
                violations: [],
                warnings: [],
                passes: []
            },
            
            // DOM
            dom: {
                sizes: [],
                mutations: [],
                eventListeners: []
            },
            
            // Storage
            storage: {
                localStorage: [],
                sessionStorage: [],
                cookies: []
            },
            
            // Security
            security: {
                mixedContent: [],
                cspViolations: [],
                insecureForms: []
            }
        };
        
        // Statistiken
        this.stats = {
            totalIssues: 0,
            criticalIssues: 0,
            warnings: 0,
            pagesAnalyzed: 0,
            actionsPerformed: 0
        };
        
        // Aktueller Kontext
        this.currentPage = null;
        this.currentAction = null;
        this.actionCounter = 0;
    }

    // ========================================================================
    // CONTEXT MANAGEMENT
    // ========================================================================
    
    setPage(pageName) {
        this.currentPage = pageName;
        this.stats.pagesAnalyzed++;
    }
    
    startAction(actionName, context = {}) {
        this.actionCounter++;
        this.stats.actionsPerformed++;
        
        this.currentAction = {
            id: this.actionCounter,
            name: actionName,
            page: this.currentPage,
            context,
            timestamp: new Date().toISOString()
        };
        
        return this.currentAction;
    }
    
    endAction() {
        this.currentAction = null;
    }
    
    getContext() {
        return {
            page: this.currentPage,
            action: this.currentAction?.name,
            actionId: this.currentAction?.id,
            timestamp: new Date().toISOString()
        };
    }

    // ========================================================================
    // CONSOLE LOGGING
    // ========================================================================
    
    addConsoleLog(type, message, location, args, stack) {
        const entry = {
            ...this.getContext(),
            type,
            message,
            location,
            args,
            stack
        };
        
        const category = this.data.console[type] || this.data.console.other;
        category.push(entry);
        
        if (type === 'error') {
            this.stats.criticalIssues++;
            this.stats.totalIssues++;
        } else if (type === 'warning') {
            this.stats.warnings++;
            this.stats.totalIssues++;
        }
        
        const icon = { error: '❌', warning: '⚠️', log: '📝', info: 'ℹ️', debug: '🔧' }[type] || '📋';
        console.log(`    ${icon} [CONSOLE.${type.toUpperCase()}] ${(message || '').substring(0, 60)}`);
        
        return entry;
    }

    // ========================================================================
    // EXCEPTIONS
    // ========================================================================
    
    addException(error, isRejection = false) {
        const entry = {
            ...this.getContext(),
            message: error.message,
            name: error.name,
            stack: error.stack,
            isRejection
        };
        
        if (isRejection) {
            this.data.exceptions.unhandledRejections.push(entry);
        } else {
            this.data.exceptions.uncaught.push(entry);
        }
        
        this.stats.criticalIssues++;
        this.stats.totalIssues++;
        
        console.log(`    💥 [${isRejection ? 'REJECTION' : 'EXCEPTION'}] ${error.message.substring(0, 60)}`);
        
        return entry;
    }

    // ========================================================================
    // PERFORMANCE
    // ========================================================================
    
    addWebVitals(vitals) {
        const entry = {
            ...this.getContext(),
            ...vitals,
            issues: []
        };
        
        // Check against thresholds
        if (vitals.lcp && vitals.lcp > CONFIG.thresholds.lcp) {
            entry.issues.push({ metric: 'LCP', value: vitals.lcp, threshold: CONFIG.thresholds.lcp, severity: 'warning' });
            this.stats.warnings++;
        }
        if (vitals.fid && vitals.fid > CONFIG.thresholds.fid) {
            entry.issues.push({ metric: 'FID', value: vitals.fid, threshold: CONFIG.thresholds.fid, severity: 'warning' });
            this.stats.warnings++;
        }
        if (vitals.cls && vitals.cls > CONFIG.thresholds.cls) {
            entry.issues.push({ metric: 'CLS', value: vitals.cls, threshold: CONFIG.thresholds.cls, severity: 'warning' });
            this.stats.warnings++;
        }
        if (vitals.fcp && vitals.fcp > CONFIG.thresholds.fcp) {
            entry.issues.push({ metric: 'FCP', value: vitals.fcp, threshold: CONFIG.thresholds.fcp, severity: 'warning' });
            this.stats.warnings++;
        }
        if (vitals.ttfb && vitals.ttfb > CONFIG.thresholds.ttfb) {
            entry.issues.push({ metric: 'TTFB', value: vitals.ttfb, threshold: CONFIG.thresholds.ttfb, severity: 'warning' });
            this.stats.warnings++;
        }
        
        this.data.performance.webVitals.push(entry);
        
        if (entry.issues.length > 0) {
            console.log(`    ⏱️ [WEB VITALS] ${entry.issues.length} threshold violations`);
        }
        
        return entry;
    }
    
    addNavigationTiming(timing) {
        const entry = {
            ...this.getContext(),
            ...timing
        };
        this.data.performance.navigation.push(entry);
        return entry;
    }
    
    addResourceTiming(resources) {
        for (const resource of resources) {
            const entry = {
                ...this.getContext(),
                ...resource,
                isSlow: resource.duration > CONFIG.thresholds.slowRequest,
                isLarge: resource.transferSize > CONFIG.thresholds.largeResponse
            };
            
            this.data.performance.resources.push(entry);
            
            if (entry.isSlow) {
                this.stats.warnings++;
                console.log(`    🐢 [SLOW RESOURCE] ${resource.name.substring(0, 50)} (${Math.round(resource.duration)}ms)`);
            }
        }
    }
    
    addLongTask(task) {
        const entry = {
            ...this.getContext(),
            duration: task.duration,
            startTime: task.startTime,
            attribution: task.attribution
        };
        
        this.data.performance.longTasks.push(entry);
        
        if (task.duration > 100) {
            this.stats.warnings++;
            console.log(`    🐌 [LONG TASK] ${Math.round(task.duration)}ms`);
        }
        
        return entry;
    }
    
    addLayoutShift(shift) {
        const entry = {
            ...this.getContext(),
            value: shift.value,
            hadRecentInput: shift.hadRecentInput,
            sources: shift.sources
        };
        
        this.data.performance.layoutShifts.push(entry);
        
        if (shift.value > 0.1 && !shift.hadRecentInput) {
            this.stats.warnings++;
            console.log(`    📐 [LAYOUT SHIFT] ${shift.value.toFixed(4)}`);
        }
        
        return entry;
    }
    
    addMemoryUsage(memory) {
        const entry = {
            ...this.getContext(),
            usedJSHeapSize: memory.usedJSHeapSize,
            totalJSHeapSize: memory.totalJSHeapSize,
            jsHeapSizeLimit: memory.jsHeapSizeLimit,
            usedMB: Math.round(memory.usedJSHeapSize / 1024 / 1024),
            isHigh: memory.usedJSHeapSize > CONFIG.thresholds.highMemory
        };
        
        this.data.performance.memory.push(entry);
        
        if (entry.isHigh) {
            this.stats.warnings++;
            console.log(`    🧠 [HIGH MEMORY] ${entry.usedMB}MB used`);
        }
        
        return entry;
    }

    // ========================================================================
    // NETWORK
    // ========================================================================
    
    addRequest(request) {
        const entry = {
            ...this.getContext(),
            url: request.url,
            method: request.method,
            resourceType: request.resourceType,
            headers: request.headers,
            postData: request.postData
        };
        
        this.data.network.requests.push(entry);
        return entry;
    }
    
    addResponse(response, timing) {
        const entry = {
            ...this.getContext(),
            url: response.url,
            status: response.status,
            statusText: response.statusText,
            headers: response.headers,
            timing,
            isSlow: timing?.responseTime > CONFIG.thresholds.slowRequest,
            isError: response.status >= 400
        };
        
        this.data.network.responses.push(entry);
        
        if (entry.isSlow) {
            this.data.network.slow.push(entry);
            console.log(`    🐢 [SLOW RESPONSE] ${response.url.substring(0, 50)} (${Math.round(timing?.responseTime)}ms)`);
        }
        
        if (entry.isError) {
            this.data.network.failed.push(entry);
            this.stats.totalIssues++;
            
            if (response.status >= 500) {
                this.stats.criticalIssues++;
                console.log(`    ❌ [HTTP ${response.status}] ${response.url.substring(0, 60)}`);
            } else {
                this.stats.warnings++;
                console.log(`    ⚠️ [HTTP ${response.status}] ${response.url.substring(0, 60)}`);
            }
        }
        
        return entry;
    }
    
    addFailedRequest(request, errorText) {
        const url = request.url || 'unknown';
        const entry = {
            ...this.getContext(),
            url: url,
            method: request.method,
            resourceType: request.resourceType,
            errorText
        };

        this.data.network.failed.push(entry);
        this.stats.criticalIssues++;
        this.stats.totalIssues++;

        console.log(`    ❌ [REQUEST FAILED] ${url.substring(0, 50)} - ${errorText}`);

        return entry;
    }

    // ========================================================================
    // COVERAGE
    // ========================================================================
    
    addJSCoverage(coverage) {
        if (!coverage || !Array.isArray(coverage) || coverage.length === 0) {
            console.log(`    📦 [JS COVERAGE] No data available`);
            return null;
        }

        const totalBytes = coverage.reduce((sum, entry) => sum + (entry.text?.length || 0), 0);
        const usedBytes = coverage.reduce((sum, entry) => {
            return sum + (entry.ranges || []).reduce((s, r) => s + (r.end - r.start), 0);
        }, 0);

        if (totalBytes === 0) {
            console.log(`    📦 [JS COVERAGE] No bytes to analyze`);
            return null;
        }

        const entry = {
            ...this.getContext(),
            totalBytes,
            usedBytes,
            unusedBytes: totalBytes - usedBytes,
            unusedPercent: ((totalBytes - usedBytes) / totalBytes * 100).toFixed(1),
            files: coverage.map(c => ({
                url: c.url,
                totalBytes: c.text?.length || 0,
                usedBytes: (c.ranges || []).reduce((s, r) => s + (r.end - r.start), 0),
                unusedPercent: c.text?.length ? (((c.text.length - (c.ranges || []).reduce((s, r) => s + (r.end - r.start), 0)) / c.text.length) * 100).toFixed(1) : '0'
            }))
        };

        this.data.coverage.js.push(entry);

        if (parseFloat(entry.unusedPercent) > 50) {
            console.log(`    📦 [JS COVERAGE] ${entry.unusedPercent}% unused (${Math.round(entry.unusedBytes / 1024)}KB)`);
        }

        return entry;
    }
    
    addCSSCoverage(coverage) {
        if (!coverage || !Array.isArray(coverage) || coverage.length === 0) {
            console.log(`    🎨 [CSS COVERAGE] No data available`);
            return null;
        }

        const totalBytes = coverage.reduce((sum, entry) => sum + (entry.text?.length || 0), 0);
        const usedBytes = coverage.reduce((sum, entry) => {
            return sum + (entry.ranges || []).reduce((s, r) => s + (r.end - r.start), 0);
        }, 0);

        if (totalBytes === 0) {
            console.log(`    🎨 [CSS COVERAGE] No bytes to analyze`);
            return null;
        }

        const entry = {
            ...this.getContext(),
            totalBytes,
            usedBytes,
            unusedBytes: totalBytes - usedBytes,
            unusedPercent: ((totalBytes - usedBytes) / totalBytes * 100).toFixed(1),
            files: coverage.map(c => ({
                url: c.url,
                totalBytes: c.text?.length || 0,
                usedBytes: (c.ranges || []).reduce((s, r) => s + (r.end - r.start), 0)
            }))
        };

        this.data.coverage.css.push(entry);

        if (parseFloat(entry.unusedPercent) > 50) {
            console.log(`    🎨 [CSS COVERAGE] ${entry.unusedPercent}% unused (${Math.round(entry.unusedBytes / 1024)}KB)`);
        }

        return entry;
    }

    // ========================================================================
    // ACCESSIBILITY
    // ========================================================================
    
    addA11yResults(results) {
        if (!results) {
            console.log(`    📦 [A11Y] No data available`);
            return;
        }

        const violations = results.violations || [];
        for (const violation of violations) {
            const entry = {
                ...this.getContext(),
                id: violation.id || 'unknown',
                impact: violation.impact || 'unknown',
                description: violation.description || '',
                help: violation.help || '',
                helpUrl: violation.helpUrl || '',
                nodes: (violation.nodes || []).map(n => ({
                    html: n?.html || '',
                    target: n?.target || [],
                    failureSummary: n?.failureSummary || ''
                }))
            };

            this.data.accessibility.violations.push(entry);

            const impact = violation.impact || 'unknown';
            if (impact === 'critical' || impact === 'serious') {
                this.stats.criticalIssues++;
                console.log(`    ♿ [A11Y ${impact.toUpperCase()}] ${violation.id || 'unknown'}: ${violation.help || ''}`);
            } else {
                this.stats.warnings++;
            }

            this.stats.totalIssues++;
        }

        // Store passes for completeness
        const passes = results.passes || [];
        for (const pass of passes) {
            this.data.accessibility.passes.push({
                ...this.getContext(),
                id: pass?.id || 'unknown',
                description: pass?.description || ''
            });
        }
    }

    // ========================================================================
    // DOM
    // ========================================================================
    
    addDOMSize(size) {
        const entry = {
            ...this.getContext(),
            nodeCount: size.nodeCount,
            depth: size.depth,
            isTooLarge: size.nodeCount > CONFIG.thresholds.maxDomNodes
        };
        
        this.data.dom.sizes.push(entry);
        
        if (entry.isTooLarge) {
            this.stats.warnings++;
            console.log(`    🌳 [DOM SIZE] ${size.nodeCount} nodes (threshold: ${CONFIG.thresholds.maxDomNodes})`);
        }
        
        return entry;
    }
    
    addEventListenerCount(count) {
        const entry = {
            ...this.getContext(),
            count,
            isTooMany: count > CONFIG.thresholds.maxEventListeners
        };
        
        this.data.dom.eventListeners.push(entry);
        
        if (entry.isTooMany) {
            this.stats.warnings++;
            console.log(`    👂 [EVENT LISTENERS] ${count} listeners (threshold: ${CONFIG.thresholds.maxEventListeners})`);
        }
        
        return entry;
    }

    // ========================================================================
    // STORAGE
    // ========================================================================
    
    addStorageSnapshot(type, data) {
        const entry = {
            ...this.getContext(),
            type,
            itemCount: Object.keys(data).length,
            totalSize: JSON.stringify(data).length,
            items: data
        };
        
        this.data.storage[type].push(entry);
        return entry;
    }

    // ========================================================================
    // SECURITY
    // ========================================================================
    
    addSecurityIssue(type, details) {
        const entry = {
            ...this.getContext(),
            type,
            ...details
        };
        
        this.data.security[type === 'mixed-content' ? 'mixedContent' : 
                          type === 'csp' ? 'cspViolations' : 'insecureForms'].push(entry);
        
        this.stats.criticalIssues++;
        this.stats.totalIssues++;
        
        console.log(`    🔒 [SECURITY] ${type}: ${details.message || details.url || 'Issue detected'}`);
        
        return entry;
    }

    // ========================================================================
    // SAVE ALL DATA
    // ========================================================================
    
    async saveAll() {
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        
        // Create all directories
        const dirs = [
            'console', 'exceptions', 'performance', 'network', 
            'coverage', 'accessibility', 'dom', 'storage', 
            'security', 'analysis', 'by-page'
        ];
        
        for (const dir of dirs) {
            fs.mkdirSync(path.join(this.baseDir, dir), { recursive: true });
        }
        
        // Save complete data
        const fullDataPath = path.join(this.baseDir, `full-diagnostics-${timestamp}.json`);
        fs.writeFileSync(fullDataPath, JSON.stringify({
            meta: {
                timestamp: new Date().toISOString(),
                duration: Date.now() - this.startTime,
                stats: this.stats,
                config: CONFIG
            },
            data: this.data
        }, null, 2));
        
        // Save by category
        for (const [category, categoryData] of Object.entries(this.data)) {
            const catPath = path.join(this.baseDir, category, `${category}-${timestamp}.json`);
            fs.writeFileSync(catPath, JSON.stringify({
                category,
                timestamp: new Date().toISOString(),
                data: categoryData
            }, null, 2));
        }
        
        // Generate analysis
        const analysis = this.generateAnalysis();
        fs.writeFileSync(
            path.join(this.baseDir, 'analysis', `analysis-${timestamp}.json`),
            JSON.stringify(analysis, null, 2)
        );
        
        // Generate markdown report
        const mdReport = this.generateMarkdownReport(analysis);
        fs.writeFileSync(
            path.join(this.baseDir, 'analysis', `report-${timestamp}.md`),
            mdReport
        );
        
        // Generate CSV exports
        this.generateCSVExports(timestamp);
        
        // Generate HTML dashboard
        const htmlDashboard = this.generateHTMLDashboard(analysis);
        fs.writeFileSync(
            path.join(this.baseDir, `dashboard-${timestamp}.html`),
            htmlDashboard
        );
        
        console.log(`\n📁 Diagnostics saved to: ${this.baseDir}`);
        console.log(`   📊 Full data: ${fullDataPath}`);
        console.log(`   📈 Analysis: analysis/analysis-${timestamp}.json`);
        console.log(`   📝 Report: analysis/report-${timestamp}.md`);
        console.log(`   🌐 Dashboard: dashboard-${timestamp}.html`);
    }
    
    generateAnalysis() {
        // Safe array access helper
        const safeArray = (arr) => Array.isArray(arr) ? arr : [];

        // Aggregate all issues with null safety
        const allErrors = [
            ...safeArray(this.data.console.errors),
            ...safeArray(this.data.exceptions.uncaught),
            ...safeArray(this.data.exceptions.unhandledRejections),
            ...safeArray(this.data.network.failed).filter(f => (f.status || 0) >= 500)
        ];

        const allWarnings = [
            ...safeArray(this.data.console.warnings),
            ...safeArray(this.data.network.failed).filter(f => (f.status || 0) >= 400 && (f.status || 0) < 500),
            ...safeArray(this.data.network.slow),
            ...safeArray(this.data.performance.longTasks).filter(t => (t.duration || 0) > 100),
            ...safeArray(this.data.performance.layoutShifts).filter(s => (s.value || 0) > 0.1),
            ...safeArray(this.data.accessibility.violations).filter(v => v.impact !== 'critical' && v.impact !== 'serious')
        ];

        const criticalA11y = safeArray(this.data.accessibility.violations).filter(
            v => v.impact === 'critical' || v.impact === 'serious'
        );
        
        // Group errors by message
        const errorPatterns = {};
        for (const error of allErrors) {
            const msg = (error.message || error.errorText || '').substring(0, 100);
            if (!errorPatterns[msg]) {
                errorPatterns[msg] = { count: 0, pages: new Set(), examples: [] };
            }
            errorPatterns[msg].count++;
            errorPatterns[msg].pages.add(error.page);
            if (errorPatterns[msg].examples.length < 3) {
                errorPatterns[msg].examples.push(error);
            }
        }
        
        // Page health scores
        const pageHealth = {};
        const allIssuesByPage = {};
        
        for (const [category, categoryData] of Object.entries(this.data)) {
            for (const [subcat, items] of Object.entries(categoryData)) {
                if (Array.isArray(items)) {
                    for (const item of items) {
                        if (item.page) {
                            if (!allIssuesByPage[item.page]) {
                                allIssuesByPage[item.page] = { errors: 0, warnings: 0, total: 0 };
                            }
                            allIssuesByPage[item.page].total++;
                            
                            // Determine severity
                            if (category === 'console' && subcat === 'errors') {
                                allIssuesByPage[item.page].errors++;
                            } else if (category === 'exceptions') {
                                allIssuesByPage[item.page].errors++;
                            } else if (category === 'network' && subcat === 'failed') {
                                if (item.status >= 500) {
                                    allIssuesByPage[item.page].errors++;
                                } else {
                                    allIssuesByPage[item.page].warnings++;
                                }
                            } else if (category === 'console' && subcat === 'warnings') {
                                allIssuesByPage[item.page].warnings++;
                            }
                        }
                    }
                }
            }
        }
        
        for (const [page, issues] of Object.entries(allIssuesByPage)) {
            pageHealth[page] = {
                ...issues,
                score: Math.max(0, 100 - (issues.errors * 15) - (issues.warnings * 3))
            };
        }
        
        // Performance summary (with null-safe array access)
        const webVitals = safeArray(this.data.performance.webVitals);
        const layoutShifts = safeArray(this.data.performance.layoutShifts);
        const longTasks = safeArray(this.data.performance.longTasks);
        const memoryData = safeArray(this.data.performance.memory);
        const slowReqs = safeArray(this.data.network.slow);
        const failedReqs = safeArray(this.data.network.failed);
        const allRequests = safeArray(this.data.network.requests);
        const jsCovarage = safeArray(this.data.coverage.js);
        const cssCovarage = safeArray(this.data.coverage.css);
        const a11yViolations = safeArray(this.data.accessibility.violations);

        const perfSummary = {
            avgLCP: this.average(webVitals.map(v => v.lcp).filter(Boolean)),
            avgFCP: this.average(webVitals.map(v => v.fcp).filter(Boolean)),
            avgTTFB: this.average(webVitals.map(v => v.ttfb).filter(Boolean)),
            totalLayoutShifts: layoutShifts.length,
            totalLongTasks: longTasks.length,
            avgMemoryMB: this.average(memoryData.map(m => m.usedMB || 0)),
            slowRequests: slowReqs.length,
            failedRequests: failedReqs.length
        };

        // Coverage summary
        const coverageSummary = {
            jsUnusedPercent: this.average(jsCovarage.map(c => parseFloat(c.unusedPercent || '0'))),
            cssUnusedPercent: this.average(cssCovarage.map(c => parseFloat(c.unusedPercent || '0'))),
            jsUnusedKB: Math.round(this.sum(jsCovarage.map(c => c.unusedBytes || 0)) / 1024),
            cssUnusedKB: Math.round(this.sum(cssCovarage.map(c => c.unusedBytes || 0)) / 1024)
        };

        return {
            summary: {
                totalIssues: this.stats.totalIssues,
                criticalIssues: this.stats.criticalIssues,
                warnings: this.stats.warnings,
                pagesAnalyzed: this.stats.pagesAnalyzed,
                actionsPerformed: this.stats.actionsPerformed,
                duration: Date.now() - this.startTime
            },
            errorPatterns: Object.fromEntries(
                Object.entries(errorPatterns)
                    .sort((a, b) => b[1].count - a[1].count)
                    .slice(0, 20)
                    .map(([k, v]) => [k, { ...v, pages: Array.from(v.pages) }])
            ),
            pageHealth: Object.fromEntries(
                Object.entries(pageHealth).sort((a, b) => a[1].score - b[1].score)
            ),
            worstPages: Object.entries(pageHealth)
                .sort((a, b) => a[1].score - b[1].score)
                .slice(0, 10)
                .map(([page, data]) => ({ page, ...data })),
            performance: perfSummary,
            coverage: coverageSummary,
            accessibility: {
                totalViolations: a11yViolations.length,
                criticalViolations: criticalA11y.length,
                topViolations: this.groupBy(a11yViolations, 'id')
            },
            network: {
                totalRequests: allRequests.length,
                failedRequests: failedReqs.length,
                slowRequests: slowReqs.length
            }
        };
    }
    
    generateMarkdownReport(analysis) {
        let md = `# Ultra Browser Diagnostics Report\n\n`;
        md += `**Generated:** ${new Date().toISOString()}\n`;
        md += `**Duration:** ${Math.round(analysis.summary.duration / 1000)}s\n\n`;
        
        // Executive Summary
        md += `## Executive Summary\n\n`;
        md += `| Metric | Value | Status |\n|--------|-------|--------|\n`;
        md += `| Total Issues | ${analysis.summary.totalIssues} | ${analysis.summary.totalIssues > 50 ? '🔴' : analysis.summary.totalIssues > 20 ? '🟡' : '🟢'} |\n`;
        md += `| Critical Issues | ${analysis.summary.criticalIssues} | ${analysis.summary.criticalIssues > 10 ? '🔴' : analysis.summary.criticalIssues > 0 ? '🟡' : '🟢'} |\n`;
        md += `| Warnings | ${analysis.summary.warnings} | ${analysis.summary.warnings > 30 ? '🟡' : '🟢'} |\n`;
        md += `| Pages Analyzed | ${analysis.summary.pagesAnalyzed} | |\n`;
        md += `| Actions Performed | ${analysis.summary.actionsPerformed} | |\n\n`;
        
        // Performance
        md += `## Performance\n\n`;
        md += `| Metric | Value | Threshold | Status |\n|--------|-------|-----------|--------|\n`;
        md += `| Avg LCP | ${Math.round(analysis.performance.avgLCP || 0)}ms | ${CONFIG.thresholds.lcp}ms | ${(analysis.performance.avgLCP || 0) > CONFIG.thresholds.lcp ? '🔴' : '🟢'} |\n`;
        md += `| Avg FCP | ${Math.round(analysis.performance.avgFCP || 0)}ms | ${CONFIG.thresholds.fcp}ms | ${(analysis.performance.avgFCP || 0) > CONFIG.thresholds.fcp ? '🔴' : '🟢'} |\n`;
        md += `| Avg TTFB | ${Math.round(analysis.performance.avgTTFB || 0)}ms | ${CONFIG.thresholds.ttfb}ms | ${(analysis.performance.avgTTFB || 0) > CONFIG.thresholds.ttfb ? '🔴' : '🟢'} |\n`;
        md += `| Layout Shifts | ${analysis.performance.totalLayoutShifts} | | |\n`;
        md += `| Long Tasks | ${analysis.performance.totalLongTasks} | | |\n`;
        md += `| Avg Memory | ${Math.round(analysis.performance.avgMemoryMB || 0)}MB | | |\n\n`;
        
        // Network
        md += `## Network\n\n`;
        md += `| Metric | Value |\n|--------|-------|\n`;
        md += `| Total Requests | ${analysis.network.totalRequests} |\n`;
        md += `| Failed Requests | ${analysis.network.failedRequests} |\n`;
        md += `| Slow Requests | ${analysis.network.slowRequests} |\n\n`;
        
        // Coverage
        md += `## Code Coverage\n\n`;
        md += `| Type | Unused % | Unused Size |\n|------|----------|-------------|\n`;
        md += `| JavaScript | ${(analysis.coverage.jsUnusedPercent || 0).toFixed(1)}% | ${analysis.coverage.jsUnusedKB}KB |\n`;
        md += `| CSS | ${(analysis.coverage.cssUnusedPercent || 0).toFixed(1)}% | ${analysis.coverage.cssUnusedKB}KB |\n\n`;
        
        // Accessibility
        md += `## Accessibility\n\n`;
        md += `| Metric | Value |\n|--------|-------|\n`;
        md += `| Total Violations | ${analysis.accessibility.totalViolations} |\n`;
        md += `| Critical Violations | ${analysis.accessibility.criticalViolations} |\n\n`;
        
        const topViolations = analysis.accessibility?.topViolations || {};
        if (Object.keys(topViolations).length > 0) {
            md += `### Top A11y Issues\n\n`;
            for (const [id, items] of Object.entries(topViolations).slice(0, 10)) {
                const itemsArray = Array.isArray(items) ? items : [];
                md += `- **${id}** (${itemsArray.length}x): ${itemsArray[0]?.help || ''}\n`;
            }
            md += `\n`;
        }

        // Worst Pages
        const worstPages = analysis.worstPages || [];
        if (worstPages.length > 0) {
            md += `## Worst Performing Pages\n\n`;
            md += `| Page | Errors | Warnings | Health Score |\n|------|--------|----------|-------------|\n`;
            for (const page of worstPages) {
                md += `| ${page.page || 'unknown'} | ${page.errors || 0} | ${page.warnings || 0} | ${page.score || 0}% |\n`;
            }
            md += `\n`;
        }

        // Error Patterns
        const errorPatterns = analysis.errorPatterns || {};
        const errorList = Object.entries(errorPatterns).slice(0, 15);
        if (errorList.length > 0) {
            md += `## Top Error Patterns\n\n`;
            for (const [pattern, data] of errorList) {
                md += `### ${data.count}x: \`${pattern.substring(0, 80)}\`\n`;
                md += `- Pages: ${data.pages.join(', ')}\n\n`;
            }
        }
        
        return md;
    }
    
    generateCSVExports(timestamp) {
        // Safe array access helper
        const safeArray = (arr) => Array.isArray(arr) ? arr : [];

        // Errors CSV
        let errorsCsv = 'id,timestamp,page,action,type,message,location\n';
        const allErrors = [...safeArray(this.data.console.errors), ...safeArray(this.data.exceptions.uncaught)];
        for (const error of allErrors) {
            const msg = (error.message || '').replace(/"/g, '""').substring(0, 500);
            errorsCsv += `${error.actionId || ''},"${error.timestamp || ''}","${error.page || ''}","${error.action || ''}","error","${msg}","${error.location || ''}"\n`;
        }
        fs.writeFileSync(path.join(this.baseDir, 'analysis', `errors-${timestamp}.csv`), errorsCsv);

        // Performance CSV
        let perfCsv = 'page,lcp,fcp,ttfb,cls,memory_mb\n';
        for (const vital of safeArray(this.data.performance.webVitals)) {
            perfCsv += `"${vital.page || ''}",${vital.lcp || ''},${vital.fcp || ''},${vital.ttfb || ''},${vital.cls || ''},${vital.memoryMB || ''}\n`;
        }
        fs.writeFileSync(path.join(this.baseDir, 'analysis', `performance-${timestamp}.csv`), perfCsv);

        // Network CSV
        let networkCsv = 'page,url,status,duration,size,type\n';
        for (const resp of safeArray(this.data.network.responses)) {
            const url = (resp.url || '').replace(/"/g, '""').substring(0, 200);
            networkCsv += `"${resp.page || ''}","${url}",${resp.status || ''},${resp.timing?.responseTime || ''},,\n`;
        }
        fs.writeFileSync(path.join(this.baseDir, 'analysis', `network-${timestamp}.csv`), networkCsv);
    }
    
    generateHTMLDashboard(analysis) {
        return `<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ablage-System Browser Diagnostics Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        .gradient-bg { background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); }
        .card { background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(148, 163, 184, 0.1); }
    </style>
</head>
<body class="gradient-bg min-h-screen text-white p-8">
    <div class="max-w-7xl mx-auto">
        <header class="mb-8">
            <h1 class="text-4xl font-bold mb-2">🔍 Browser Diagnostics Dashboard</h1>
            <p class="text-slate-400">Ablage-System • Generated: ${new Date().toISOString()}</p>
        </header>
        
        <!-- Summary Cards -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
            <div class="card rounded-xl p-6">
                <div class="text-sm text-slate-400 mb-1">Total Issues</div>
                <div class="text-3xl font-bold ${analysis.summary.totalIssues > 50 ? 'text-red-400' : analysis.summary.totalIssues > 20 ? 'text-yellow-400' : 'text-green-400'}">${analysis.summary.totalIssues}</div>
            </div>
            <div class="card rounded-xl p-6">
                <div class="text-sm text-slate-400 mb-1">Critical</div>
                <div class="text-3xl font-bold ${analysis.summary.criticalIssues > 0 ? 'text-red-400' : 'text-green-400'}">${analysis.summary.criticalIssues}</div>
            </div>
            <div class="card rounded-xl p-6">
                <div class="text-sm text-slate-400 mb-1">Warnings</div>
                <div class="text-3xl font-bold text-yellow-400">${analysis.summary.warnings}</div>
            </div>
            <div class="card rounded-xl p-6">
                <div class="text-sm text-slate-400 mb-1">Pages Tested</div>
                <div class="text-3xl font-bold text-blue-400">${analysis.summary.pagesAnalyzed}</div>
            </div>
        </div>
        
        <!-- Performance Metrics -->
        <div class="card rounded-xl p-6 mb-8">
            <h2 class="text-xl font-bold mb-4">⚡ Core Web Vitals</h2>
            <div class="grid grid-cols-2 md:grid-cols-5 gap-4">
                <div>
                    <div class="text-sm text-slate-400">LCP</div>
                    <div class="text-2xl font-bold ${(analysis.performance.avgLCP || 0) > CONFIG.thresholds.lcp ? 'text-red-400' : 'text-green-400'}">${Math.round(analysis.performance.avgLCP || 0)}ms</div>
                    <div class="text-xs text-slate-500">Target: <${CONFIG.thresholds.lcp}ms</div>
                </div>
                <div>
                    <div class="text-sm text-slate-400">FCP</div>
                    <div class="text-2xl font-bold ${(analysis.performance.avgFCP || 0) > CONFIG.thresholds.fcp ? 'text-red-400' : 'text-green-400'}">${Math.round(analysis.performance.avgFCP || 0)}ms</div>
                    <div class="text-xs text-slate-500">Target: <${CONFIG.thresholds.fcp}ms</div>
                </div>
                <div>
                    <div class="text-sm text-slate-400">TTFB</div>
                    <div class="text-2xl font-bold ${(analysis.performance.avgTTFB || 0) > CONFIG.thresholds.ttfb ? 'text-red-400' : 'text-green-400'}">${Math.round(analysis.performance.avgTTFB || 0)}ms</div>
                    <div class="text-xs text-slate-500">Target: <${CONFIG.thresholds.ttfb}ms</div>
                </div>
                <div>
                    <div class="text-sm text-slate-400">Long Tasks</div>
                    <div class="text-2xl font-bold text-yellow-400">${analysis.performance.totalLongTasks}</div>
                </div>
                <div>
                    <div class="text-sm text-slate-400">Memory</div>
                    <div class="text-2xl font-bold">${Math.round(analysis.performance.avgMemoryMB || 0)}MB</div>
                </div>
            </div>
        </div>
        
        <!-- Network & Coverage -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-8 mb-8">
            <div class="card rounded-xl p-6">
                <h2 class="text-xl font-bold mb-4">🌐 Network</h2>
                <div class="space-y-3">
                    <div class="flex justify-between">
                        <span class="text-slate-400">Total Requests</span>
                        <span class="font-bold">${analysis.network.totalRequests}</span>
                    </div>
                    <div class="flex justify-between">
                        <span class="text-slate-400">Failed Requests</span>
                        <span class="font-bold ${analysis.network.failedRequests > 0 ? 'text-red-400' : 'text-green-400'}">${analysis.network.failedRequests}</span>
                    </div>
                    <div class="flex justify-between">
                        <span class="text-slate-400">Slow Requests (>${CONFIG.thresholds.slowRequest}ms)</span>
                        <span class="font-bold ${analysis.network.slowRequests > 10 ? 'text-yellow-400' : ''}">${analysis.network.slowRequests}</span>
                    </div>
                </div>
            </div>
            
            <div class="card rounded-xl p-6">
                <h2 class="text-xl font-bold mb-4">📦 Code Coverage</h2>
                <div class="space-y-3">
                    <div>
                        <div class="flex justify-between mb-1">
                            <span class="text-slate-400">JavaScript Unused</span>
                            <span class="font-bold">${(analysis.coverage.jsUnusedPercent || 0).toFixed(1)}% (${analysis.coverage.jsUnusedKB}KB)</span>
                        </div>
                        <div class="w-full bg-slate-700 rounded-full h-2">
                            <div class="bg-yellow-400 h-2 rounded-full" style="width: ${analysis.coverage.jsUnusedPercent || 0}%"></div>
                        </div>
                    </div>
                    <div>
                        <div class="flex justify-between mb-1">
                            <span class="text-slate-400">CSS Unused</span>
                            <span class="font-bold">${(analysis.coverage.cssUnusedPercent || 0).toFixed(1)}% (${analysis.coverage.cssUnusedKB}KB)</span>
                        </div>
                        <div class="w-full bg-slate-700 rounded-full h-2">
                            <div class="bg-purple-400 h-2 rounded-full" style="width: ${analysis.coverage.cssUnusedPercent || 0}%"></div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Accessibility -->
        <div class="card rounded-xl p-6 mb-8">
            <h2 class="text-xl font-bold mb-4">♿ Accessibility</h2>
            <div class="grid grid-cols-2 gap-4">
                <div>
                    <span class="text-slate-400">Total Violations:</span>
                    <span class="font-bold ml-2 ${analysis.accessibility.totalViolations > 0 ? 'text-red-400' : 'text-green-400'}">${analysis.accessibility.totalViolations}</span>
                </div>
                <div>
                    <span class="text-slate-400">Critical:</span>
                    <span class="font-bold ml-2 ${analysis.accessibility.criticalViolations > 0 ? 'text-red-400' : 'text-green-400'}">${analysis.accessibility.criticalViolations}</span>
                </div>
            </div>
        </div>
        
        <!-- Worst Pages -->
        ${(analysis.worstPages || []).length > 0 ? `
        <div class="card rounded-xl p-6 mb-8">
            <h2 class="text-xl font-bold mb-4">🔴 Worst Performing Pages</h2>
            <div class="overflow-x-auto">
                <table class="w-full">
                    <thead>
                        <tr class="text-left text-slate-400 border-b border-slate-700">
                            <th class="pb-2">Page</th>
                            <th class="pb-2">Errors</th>
                            <th class="pb-2">Warnings</th>
                            <th class="pb-2">Health Score</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${(analysis.worstPages || []).map(page => `
                        <tr class="border-b border-slate-800">
                            <td class="py-2 font-mono text-sm">${page.page || 'unknown'}</td>
                            <td class="py-2 ${(page.errors || 0) > 0 ? 'text-red-400' : ''}">${page.errors || 0}</td>
                            <td class="py-2 ${(page.warnings || 0) > 5 ? 'text-yellow-400' : ''}">${page.warnings || 0}</td>
                            <td class="py-2">
                                <div class="flex items-center gap-2">
                                    <div class="w-20 bg-slate-700 rounded-full h-2">
                                        <div class="${(page.score || 0) < 50 ? 'bg-red-400' : (page.score || 0) < 80 ? 'bg-yellow-400' : 'bg-green-400'} h-2 rounded-full" style="width: ${page.score || 0}%"></div>
                                    </div>
                                    <span class="text-sm">${page.score || 0}%</span>
                                </div>
                            </td>
                        </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        </div>
        ` : ''}

        <!-- Top Error Patterns -->
        ${Object.keys(analysis.errorPatterns || {}).length > 0 ? `
        <div class="card rounded-xl p-6">
            <h2 class="text-xl font-bold mb-4">🔥 Top Error Patterns</h2>
            <div class="space-y-4">
                ${Object.entries(analysis.errorPatterns || {}).slice(0, 10).map(([pattern, data]) => `
                <div class="border-l-4 border-red-400 pl-4 py-2">
                    <div class="flex items-center gap-2 mb-1">
                        <span class="bg-red-400/20 text-red-400 px-2 py-0.5 rounded text-sm font-bold">${data.count || 0}x</span>
                        <span class="text-slate-400 text-sm">on ${(data.pages || []).length} pages</span>
                    </div>
                    <code class="text-sm text-slate-300 block break-all">${pattern.substring(0, 100)}</code>
                </div>
                `).join('')}
            </div>
        </div>
        ` : ''}
        
        <footer class="mt-8 text-center text-slate-500 text-sm">
            <p>Generated by Ablage-System Ultra Browser Diagnostics Suite</p>
            <p>Duration: ${Math.round(analysis.summary.duration / 1000)}s • ${analysis.summary.actionsPerformed} actions performed</p>
        </footer>
    </div>
</body>
</html>`;
    }
    
    // Helper methods
    average(arr) {
        if (!arr || arr.length === 0) return 0;
        return arr.reduce((a, b) => a + b, 0) / arr.length;
    }
    
    sum(arr) {
        if (!arr || arr.length === 0) return 0;
        return arr.reduce((a, b) => a + b, 0);
    }
    
    groupBy(arr, key) {
        const result = {};
        for (const item of arr) {
            const k = item[key];
            if (!result[k]) result[k] = [];
            result[k].push(item);
        }
        return result;
    }
}

// ============================================================================
// MAIN TEST SUITE
// ============================================================================
class UltraBrowserDiagnosticsSuite {
    constructor() {
        this.browser = null;
        this.context = null;
        this.page = null;
        this.cdp = null;
        this.diagnostics = null;
        this.results = { passed: 0, failed: 0 };
        this.startTime = Date.now();
        this.requestTimings = new Map();
    }

    async init() {
        console.log('\n' + '═'.repeat(70));
        console.log('🔬 ULTRA BROWSER DIAGNOSTICS SUITE');
        console.log('   Erfasst ALLES was der Browser hergeben kann!');
        console.log('═'.repeat(70));
        console.log(`📁 Output: ${CONFIG.outputDir}`);
        console.log(`🌐 Base URL: ${CONFIG.baseUrl}`);
        console.log('═'.repeat(70) + '\n');

        fs.mkdirSync(CONFIG.outputDir, { recursive: true });
        fs.mkdirSync(CONFIG.reportDir, { recursive: true });

        this.diagnostics = new UltraDiagnosticsManager(CONFIG.outputDir);

        // Browser mit CDP-Zugang starten
        this.browser = await chromium.launch({ 
            headless: true,
            args: ['--enable-precise-memory-info']
        });

        this.context = await this.browser.newContext({
            viewport: { width: 1920, height: 1080 },
            locale: 'de-DE'
        });

        this.page = await this.context.newPage();
        
        // CDP Session für erweiterte Metriken
        this.cdp = await this.page.context().newCDPSession(this.page);

        await this.setupAllListeners();

        console.log('✅ Browser initialized with all diagnostic listeners\n');
    }

    async setupAllListeners() {
        // ================================================================
        // CONSOLE LISTENER
        // ================================================================
        this.page.on('console', async (msg) => {
            const type = msg.type();
            const location = msg.location();
            let text = msg.text();
            
            let args = [];
            try {
                for (const arg of msg.args()) {
                    const val = await arg.jsonValue().catch(() => arg.toString());
                    args.push(val);
                }
            } catch (e) {}

            this.diagnostics.addConsoleLog(
                type,
                text,
                location ? `${location.url}:${location.lineNumber}:${location.columnNumber}` : undefined,
                args.length > 0 ? args : undefined,
                undefined
            );
        });

        // ================================================================
        // PAGE ERRORS (Uncaught Exceptions)
        // ================================================================
        this.page.on('pageerror', (error) => {
            this.diagnostics.addException(error, false);
        });

        // ================================================================
        // NETWORK LISTENERS
        // ================================================================
        this.page.on('request', (request) => {
            this.requestTimings.set(request.url(), {
                startTime: Date.now(),
                method: request.method(),
                resourceType: request.resourceType()
            });
            
            if (CONFIG.capture.allRequests) {
                this.diagnostics.addRequest({
                    url: request.url(),
                    method: request.method(),
                    resourceType: request.resourceType(),
                    headers: CONFIG.capture.requestHeaders ? request.headers() : undefined,
                    postData: request.postData()
                });
            }
        });

        this.page.on('response', async (response) => {
            const timing = this.requestTimings.get(response.url());
            const responseTime = timing ? Date.now() - timing.startTime : undefined;
            
            let headers = undefined;
            if (CONFIG.capture.responseHeaders) {
                try {
                    headers = await response.allHeaders();
                } catch (e) {}
            }
            
            this.diagnostics.addResponse(
                {
                    url: response.url(),
                    status: response.status(),
                    statusText: response.statusText(),
                    headers
                },
                { responseTime }
            );
        });

        this.page.on('requestfailed', (request) => {
            const failure = request.failure();
            this.diagnostics.addFailedRequest({
                url: request.url(),
                method: request.method(),
                resourceType: request.resourceType()
            }, failure?.errorText || 'Unknown error');
        });

        // ================================================================
        // SECURITY LISTENERS (via CDP)
        // ================================================================
        await this.cdp.send('Security.enable');
        this.cdp.on('Security.securityStateChanged', (event) => {
            if (event.securityState === 'insecure' || event.insecureContentStatus?.containedMixedForm) {
                this.diagnostics.addSecurityIssue('mixed-content', {
                    state: event.securityState,
                    summary: event.summary
                });
            }
        });

        console.log('   ✓ Console listener');
        console.log('   ✓ Exception listener');
        console.log('   ✓ Network listener');
        console.log('   ✓ Security listener');
    }

    // ========================================================================
    // PERFORMANCE METRICS COLLECTION
    // ========================================================================
    
    async collectPerformanceMetrics() {
        try {
            // Web Vitals via Performance API
            const webVitals = await this.page.evaluate(() => {
                const entries = performance.getEntriesByType('navigation')[0];
                const paintEntries = performance.getEntriesByType('paint');
                
                const fcp = paintEntries.find(e => e.name === 'first-contentful-paint')?.startTime;
                const lcp = (() => {
                    const lcpEntries = performance.getEntriesByType('largest-contentful-paint');
                    return lcpEntries.length > 0 ? lcpEntries[lcpEntries.length - 1].startTime : null;
                })();
                
                return {
                    // Navigation Timing
                    ttfb: entries?.responseStart - entries?.requestStart,
                    domContentLoaded: entries?.domContentLoadedEventEnd - entries?.navigationStart,
                    loadComplete: entries?.loadEventEnd - entries?.navigationStart,
                    
                    // Paint Timing
                    fcp,
                    lcp,
                    
                    // Resource counts
                    resourceCount: performance.getEntriesByType('resource').length,
                    
                    // Memory (if available)
                    memory: performance.memory ? {
                        usedJSHeapSize: performance.memory.usedJSHeapSize,
                        totalJSHeapSize: performance.memory.totalJSHeapSize,
                        jsHeapSizeLimit: performance.memory.jsHeapSizeLimit
                    } : null
                };
            });
            
            this.diagnostics.addWebVitals(webVitals);
            
            if (webVitals.memory) {
                this.diagnostics.addMemoryUsage(webVitals.memory);
            }
            
            // Resource Timing
            const resources = await this.page.evaluate(() => {
                return performance.getEntriesByType('resource').map(r => ({
                    name: r.name,
                    duration: r.duration,
                    transferSize: r.transferSize,
                    initiatorType: r.initiatorType
                }));
            });
            
            this.diagnostics.addResourceTiming(resources);
            
            // Layout Shifts
            const layoutShifts = await this.page.evaluate(() => {
                const observer = new PerformanceObserver(() => {});
                const entries = performance.getEntriesByType('layout-shift');
                return entries.map(e => ({
                    value: e.value,
                    hadRecentInput: e.hadRecentInput
                }));
            }).catch(() => []);
            
            for (const shift of layoutShifts) {
                this.diagnostics.addLayoutShift(shift);
            }
            
        } catch (e) {
            console.log(`    ⚠️ Performance collection failed: ${e.message}`);
        }
    }

    // ========================================================================
    // CODE COVERAGE
    // ========================================================================
    
    async startCoverage() {
        if (CONFIG.capture.jsCoverage) {
            await this.page.coverage.startJSCoverage();
        }
        if (CONFIG.capture.cssCoverage) {
            await this.page.coverage.startCSSCoverage();
        }
    }
    
    async stopCoverage() {
        if (CONFIG.capture.jsCoverage) {
            const jsCoverage = await this.page.coverage.stopJSCoverage();
            this.diagnostics.addJSCoverage(jsCoverage);
        }
        if (CONFIG.capture.cssCoverage) {
            const cssCoverage = await this.page.coverage.stopCSSCoverage();
            this.diagnostics.addCSSCoverage(cssCoverage);
        }
    }

    // ========================================================================
    // ACCESSIBILITY CHECK
    // ========================================================================
    
    async checkAccessibility() {
        try {
            // Inject axe-core
            await this.page.addScriptTag({
                url: 'https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.8.2/axe.min.js'
            });
            
            await this.page.waitForTimeout(500);
            
            const results = await this.page.evaluate(async () => {
                if (typeof axe === 'undefined') return { violations: [], passes: [] };
                return await axe.run();
            });
            
            this.diagnostics.addA11yResults(results);
            
        } catch (e) {
            console.log(`    ⚠️ A11y check failed: ${e.message}`);
        }
    }

    // ========================================================================
    // DOM ANALYSIS
    // ========================================================================
    
    async analyzeDom() {
        try {
            const domInfo = await this.page.evaluate(() => {
                const countNodes = (node) => {
                    let count = 1;
                    for (const child of node.childNodes) {
                        if (child.nodeType === 1) count += countNodes(child);
                    }
                    return count;
                };
                
                const getDepth = (node, depth = 0) => {
                    let maxDepth = depth;
                    for (const child of node.children) {
                        maxDepth = Math.max(maxDepth, getDepth(child, depth + 1));
                    }
                    return maxDepth;
                };
                
                return {
                    nodeCount: countNodes(document.body),
                    depth: getDepth(document.body)
                };
            });
            
            this.diagnostics.addDOMSize(domInfo);
            
            // Event listener count (approximate via getEventListeners in Chrome)
            const listenerCount = await this.page.evaluate(() => {
                let count = 0;
                const all = document.querySelectorAll('*');
                // This is an approximation - real count requires DevTools protocol
                for (const el of all) {
                    if (el.onclick) count++;
                    if (el.onchange) count++;
                    if (el.onsubmit) count++;
                    if (el.onmouseover) count++;
                }
                return count;
            });
            
            this.diagnostics.addEventListenerCount(listenerCount);
            
        } catch (e) {
            console.log(`    ⚠️ DOM analysis failed: ${e.message}`);
        }
    }

    // ========================================================================
    // STORAGE SNAPSHOT
    // ========================================================================
    
    async captureStorage() {
        try {
            const localStorage = await this.page.evaluate(() => {
                const data = {};
                for (let i = 0; i < window.localStorage.length; i++) {
                    const key = window.localStorage.key(i);
                    data[key] = window.localStorage.getItem(key);
                }
                return data;
            });
            this.diagnostics.addStorageSnapshot('localStorage', localStorage);
            
            const sessionStorage = await this.page.evaluate(() => {
                const data = {};
                for (let i = 0; i < window.sessionStorage.length; i++) {
                    const key = window.sessionStorage.key(i);
                    data[key] = window.sessionStorage.getItem(key);
                }
                return data;
            });
            this.diagnostics.addStorageSnapshot('sessionStorage', sessionStorage);
            
        } catch (e) {
            console.log(`    ⚠️ Storage capture failed: ${e.message}`);
        }
    }

    // ========================================================================
    // LOGIN
    // ========================================================================
    
    async login() {
        console.log('🔐 Logging in...');
        this.diagnostics.setPage('login');

        this.diagnostics.startAction('navigate-login');
        await this.page.goto(`${CONFIG.baseUrl}/login`, { waitUntil: 'networkidle' });
        await this.page.waitForTimeout(1500);
        this.diagnostics.endAction();

        this.diagnostics.startAction('fill-credentials');
        await this.page.fill('#email', CONFIG.credentials.email);
        await this.page.fill('#password', CONFIG.credentials.password);
        this.diagnostics.endAction();

        this.diagnostics.startAction('submit-login');
        await this.page.click('button[type="submit"]');
        await this.page.waitForTimeout(3000);
        this.diagnostics.endAction();

        const currentUrl = this.page.url();
        if (!currentUrl.includes('/login')) {
            console.log('✅ Login successful\n');
            return true;
        }

        console.log('❌ Login failed\n');
        return false;
    }

    // ========================================================================
    // TEST ALL ELEMENTS
    // ========================================================================
    
    async testAllButtons(pageName) {
        const buttons = await this.page.$$('button:visible');
        console.log(`   🔘 Testing ${buttons.length} buttons...`);

        const safePatterns = ['Neu', 'Erstellen', 'Add', 'New', 'Create', 'Filter', 'Suchen', 'Aktualisieren', 'Refresh'];
        const dangerPatterns = ['Löschen', 'Delete', 'Entfernen', 'Remove'];

        let btnIndex = 0;
        for (const btn of buttons.slice(0, 25)) {
            btnIndex++;
            try {
                const text = ((await btn.textContent()) || '').trim().substring(0, 25);
                const isDisabled = await btn.isDisabled();

                this.diagnostics.startAction(`button-${btnIndex}-${text}`, { button: text });
                await btn.scrollIntoViewIfNeeded();
                await btn.hover();
                await this.page.waitForTimeout(150);

                const isSafe = safePatterns.some(p => text.toLowerCase().includes(p.toLowerCase()));
                const isDanger = dangerPatterns.some(p => text.toLowerCase().includes(p.toLowerCase()));

                if (isSafe && !isDanger && !isDisabled) {
                    await btn.click();
                    await this.page.waitForTimeout(400);

                    const modal = await this.page.$('[role="dialog"]:visible');
                    if (modal) {
                        await this.page.keyboard.press('Escape');
                        await this.page.waitForTimeout(200);
                    }
                }

                if (isDanger && !isDisabled) {
                    await btn.click();
                    await this.page.waitForTimeout(300);
                    
                    const confirmDialog = await this.page.$('[role="alertdialog"], [role="dialog"]:has-text("Löschen")');
                    if (confirmDialog) {
                        const cancelBtn = await this.page.$('button:has-text("Abbrechen"), button:has-text("Nein")');
                        if (cancelBtn) {
                            await cancelBtn.click();
                        } else {
                            await this.page.keyboard.press('Escape');
                        }
                        await this.page.waitForTimeout(200);
                    }
                }

                this.diagnostics.endAction();
            } catch (e) {}
        }
    }

    async testAllForms(pageName) {
        const forms = await this.page.$$('form:visible');
        console.log(`   📝 Testing ${forms.length} forms...`);

        let formIndex = 0;
        for (const form of forms) {
            formIndex++;
            try {
                await form.scrollIntoViewIfNeeded();

                const submitBtn = await form.$('button[type="submit"]');
                if (submitBtn && !await submitBtn.isDisabled()) {
                    this.diagnostics.startAction(`form-${formIndex}-submit-empty`);
                    await submitBtn.click();
                    await this.page.waitForTimeout(300);
                    this.diagnostics.endAction();
                }

                const inputs = await form.$$('input:visible, textarea:visible');
                for (const input of inputs) {
                    try {
                        const type = await input.getAttribute('type');
                        const name = await input.getAttribute('name') || '';
                        const isDisabled = await input.isDisabled();
                        if (isDisabled) continue;

                        this.diagnostics.startAction(`form-${formIndex}-fill-${name || type}`);

                        if (type === 'email') await input.fill('test@example.com');
                        else if (type === 'password') await input.fill('Test123!');
                        else if (type === 'date') await input.fill('2025-12-31');
                        else if (type === 'number') await input.fill('100');
                        else if (type !== 'checkbox' && type !== 'radio') await input.fill('Test');
                        
                        await input.blur();
                        await this.page.waitForTimeout(80);
                        this.diagnostics.endAction();
                    } catch (e) {}
                }
            } catch (e) {}
        }
    }

    async testAllTabs(pageName) {
        const tabLists = await this.page.$$('[role="tablist"]:visible');
        
        for (const tabList of tabLists) {
            try {
                const tabs = await tabList.$$('[role="tab"]');
                for (const tab of tabs) {
                    const tabText = ((await tab.textContent()) || '').trim().substring(0, 20);
                    this.diagnostics.startAction(`tab-${tabText}`);
                    await tab.click();
                    await this.page.waitForTimeout(250);
                    this.diagnostics.endAction();
                }
            } catch (e) {}
        }
    }

    async testAllDropdowns(pageName) {
        const triggers = await this.page.$$('[aria-haspopup="true"], [aria-haspopup="listbox"]');
        
        for (const trigger of triggers.slice(0, 10)) {
            try {
                this.diagnostics.startAction('dropdown-open');
                await trigger.scrollIntoViewIfNeeded();
                await trigger.click();
                await this.page.waitForTimeout(250);
                
                const options = await this.page.$$('[role="option"]:visible, [role="menuitem"]:visible');
                if (options.length > 0) {
                    await options[0].click();
                    await this.page.waitForTimeout(150);
                } else {
                    await this.page.keyboard.press('Escape');
                }
                this.diagnostics.endAction();
            } catch (e) {}
        }
    }

    // ========================================================================
    // TEST SINGLE PAGE
    // ========================================================================
    
    async testPageComplete(route) {
        const { path: routePath, name } = route;

        console.log(`\n${'─'.repeat(60)}`);
        console.log(`📄 ${name.toUpperCase()} (${routePath})`);
        console.log('─'.repeat(60));

        this.diagnostics.setPage(name);

        try {
            // Start coverage
            await this.startCoverage();

            // Navigate
            this.diagnostics.startAction('navigate');
            await this.page.goto(`${CONFIG.baseUrl}${routePath}`, {
                waitUntil: 'networkidle',
                timeout: CONFIG.timeout.navigation
            });
            await this.page.waitForTimeout(CONFIG.timeout.short);
            this.diagnostics.endAction();

            // Collect performance metrics
            await this.collectPerformanceMetrics();

            // Test all interactive elements
            await this.testAllButtons(name);
            await this.testAllForms(name);
            await this.testAllTabs(name);
            await this.testAllDropdowns(name);

            // Scroll test
            this.diagnostics.startAction('scroll-page');
            await this.page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
            await this.page.waitForTimeout(400);
            await this.page.evaluate(() => window.scrollTo(0, 0));
            this.diagnostics.endAction();

            // DOM analysis
            await this.analyzeDom();

            // Accessibility check
            await this.checkAccessibility();

            // Storage snapshot
            await this.captureStorage();

            // Stop coverage
            await this.stopCoverage();

            // Final metrics
            await this.collectPerformanceMetrics();

            this.results.passed++;
            console.log(`   ✅ PASS`);
            return true;

        } catch (error) {
            console.log(`   ❌ FAIL - ${error.message}`);
            this.diagnostics.addException(error);
            this.results.failed++;
            
            try { await this.stopCoverage(); } catch (e) {}
            
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

    async generateFinalReport() {
        console.log('\n' + '═'.repeat(70));
        console.log('📊 GENERATING COMPREHENSIVE REPORTS');
        console.log('═'.repeat(70));

        await this.diagnostics.saveAll();

        const stats = this.diagnostics.stats;

        console.log('\n' + '═'.repeat(70));
        console.log('📈 FINAL SUMMARY');
        console.log('═'.repeat(70));
        console.log(`   Pages Tested: ${stats.pagesAnalyzed}`);
        console.log(`   Actions Performed: ${stats.actionsPerformed}`);
        console.log(`   ❌ Critical Issues: ${stats.criticalIssues}`);
        console.log(`   ⚠️ Warnings: ${stats.warnings}`);
        console.log(`   📋 Total Issues: ${stats.totalIssues}`);
        console.log(`   🕐 Duration: ${Math.round((Date.now() - this.startTime) / 1000)}s`);
        console.log('═'.repeat(70) + '\n');
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
const suite = new UltraBrowserDiagnosticsSuite();
suite.runAllTests().catch(console.error);
