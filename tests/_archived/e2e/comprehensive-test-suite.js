
    
    // ========================================================================
    // MAIN TEST RUNNER
    // ========================================================================
    
    async runAllTests() {
        console.log('╔══════════════════════════════════════════════════════════════════╗');
        console.log('║     ABLAGE-SYSTEM COMPREHENSIVE E2E TEST SUITE                   ║');
        console.log('║     Testing EVERY page, EVERY feature, EVERY button              ║');
        console.log('╚══════════════════════════════════════════════════════════════════╝');
        console.log(`\nStart Time: ${new Date().toISOString()}\n`);
        
        await this.initialize();
        
        // 1. TEST AUTH PAGES (without login)
        console.log('\n═══════════════════════════════════════════════════════════════');
        console.log('PHASE 1: AUTH PAGES (Public)');
        console.log('═══════════════════════════════════════════════════════════════');
        
        for (const route of ALL_ROUTES.auth) {
            await this.testPage(route, 'auth');
        }
        
        // 2. LOGIN
        const loginSuccess = await this.login();
        if (!loginSuccess) {
            console.log('\n❌ FATAL: Login failed. Cannot continue tests.');
            await this.generateFinalReport();
            await this.browser.close();
            return;
        }
        
        // 3. TEST ALL AUTHENTICATED ROUTES
        const routeCategories = [
            { category: 'main', name: 'MAIN PAGES', routes: ALL_ROUTES.main },
            { category: 'documents', name: 'DOCUMENT MANAGEMENT', routes: ALL_ROUTES.documents },
            { category: 'kasse', name: 'KASSENBUCH', routes: ALL_ROUTES.kasse },
            { category: 'spesen', name: 'SPESEN', routes: ALL_ROUTES.spesen },
            { category: 'streckengeschaeft', name: 'STRECKENGESCHÄFT', routes: ALL_ROUTES.streckengeschaeft },
            { category: 'finanzen', name: 'FINANZEN', routes: ALL_ROUTES.finanzen },
            { category: 'kunden', name: 'KUNDEN', routes: ALL_ROUTES.kunden },
            { category: 'lieferanten', name: 'LIEFERANTEN', routes: ALL_ROUTES.lieferanten },
            { category: 'personal', name: 'PERSONAL', routes: ALL_ROUTES.personal },
            { category: 'business-entities', name: 'BUSINESS ENTITIES', routes: ALL_ROUTES.businessEntities },
            { category: 'privat', name: 'PRIVATE DOCUMENTS', routes: ALL_ROUTES.privat },
            { category: 'admin', name: 'ADMIN - MAIN', routes: ALL_ROUTES.adminMain },
            { category: 'admin', name: 'ADMIN - OCR', routes: ALL_ROUTES.adminOcr },
            { category: 'admin', name: 'ADMIN - DATEV', routes: ALL_ROUTES.adminDatev },
            { category: 'admin', name: 'ADMIN - MAHNUNGEN', routes: ALL_ROUTES.adminMahnungen },
            { category: 'admin', name: 'ADMIN - BANKING', routes: ALL_ROUTES.adminBanking }
        ];
        
        for (const { category, name, routes } of routeCategories) {
            console.log('\n═══════════════════════════════════════════════════════════════');
            console.log(`PHASE: ${name}`);
            console.log('═══════════════════════════════════════════════════════════════');
            
            for (const route of routes) {
                await this.testPage(route, category);
            }
        }
        
        // 4. FEATURE-SPECIFIC TESTS
        console.log('\n═══════════════════════════════════════════════════════════════');
        console.log('PHASE: FEATURE-SPECIFIC TESTS');
        console.log('═══════════════════════════════════════════════════════════════');
        
        await this.testDocumentUpload();
        await this.testKasseEntryCreation();
        await this.testSpesenReportCreation();
        await this.testMahnwesenWorkflow();
        await this.testDatevExport();
        await this.testBankingReconciliation();
        await this.testOcrBackends();
        await this.testSearchFunctionality();
        await this.testChatRAG();
        
        // 5. RESPONSIVE AND THEME TESTS
        console.log('\n═══════════════════════════════════════════════════════════════');
        console.log('PHASE: RESPONSIVE & THEME TESTS');
        console.log('═══════════════════════════════════════════════════════════════');
        
        await this.testResponsiveViews();
        await this.testDarkLightMode();
        
        // 6. GENERATE FINAL REPORT
        await this.generateFinalReport();
        
        // 7. CLEANUP
        await this.browser.close();
        
        console.log('\n╔══════════════════════════════════════════════════════════════════╗');
        console.log('║                    TEST SUITE COMPLETE                           ║');
        console.log('╚══════════════════════════════════════════════════════════════════╝');
    }
    
    async generateFinalReport() {
        console.log('\n═══════════════════════════════════════════════════════════════');
        console.log('GENERATING FINAL REPORT');
        console.log('═══════════════════════════════════════════════════════════════');
        
        const report = this.results.generateReport();
        
        // JSON Report
        const jsonReportPath = path.join(CONFIG.reportDir, `test-report-${Date.now()}.json`);
        fs.writeFileSync(jsonReportPath, JSON.stringify(report, null, 2));
        console.log(`📄 JSON Report: ${jsonReportPath}`);
        
        // Human-readable Markdown Report
        const mdReport = this.generateMarkdownReport(report);
        const mdReportPath = path.join(CONFIG.reportDir, `test-report-${Date.now()}.md`);
        fs.writeFileSync(mdReportPath, mdReport);
        console.log(`📄 Markdown Report: ${mdReportPath}`);
        
        // Console Summary
        console.log('\n📊 TEST SUMMARY:');
        console.log('─────────────────────────────────────────────');
        console.log(`Total Tests:    ${report.summary.totalTests}`);
        console.log(`Passed:         ${report.summary.passed} ✅`);
        console.log(`Failed:         ${report.summary.failed} ❌`);
        console.log(`Skipped:        ${report.summary.skipped} ⏭️`);
        console.log(`Pass Rate:      ${report.summary.passRate}`);
        console.log(`Screenshots:    ${report.summary.screenshotCount} 📸`);
        console.log(`Duration:       ${report.summary.durationSeconds.toFixed(1)}s`);
        console.log('─────────────────────────────────────────────');
        
        if (report.errors.length > 0) {
            console.log('\n⚠️ ERRORS:');
            report.errors.forEach(err => {
                console.log(`  - ${err.route}: ${err.error}`);
            });
        }
        
        console.log(`\n📁 Screenshots saved to: ${CONFIG.screenshotDir}`);
        console.log(`📁 Reports saved to: ${CONFIG.reportDir}`);
    }
    
    generateMarkdownReport(report) {
        let md = `# Ablage-System Comprehensive Test Report\n\n`;
        md += `**Generated:** ${report.summary.endTime}\n\n`;
        md += `## Summary\n\n`;
        md += `| Metric | Value |\n`;
        md += `|--------|-------|\n`;
        md += `| Total Tests | ${report.summary.totalTests} |\n`;
        md += `| Passed | ${report.summary.passed} ✅ |\n`;
        md += `| Failed | ${report.summary.failed} ❌ |\n`;
        md += `| Skipped | ${report.summary.skipped} ⏭️ |\n`;
        md += `| Pass Rate | ${report.summary.passRate} |\n`;
        md += `| Screenshots | ${report.summary.screenshotCount} |\n`;
        md += `| Duration | ${report.summary.durationSeconds.toFixed(1)}s |\n\n`;
        
        md += `## Test Results by Category\n\n`;
        
        // Group results by category
        const byCategory = {};
        for (const result of report.results) {
            if (!byCategory[result.category]) {
                byCategory[result.category] = [];
            }
            byCategory[result.category].push(result);
        }
        
        for (const [category, results] of Object.entries(byCategory)) {
            md += `### ${category.toUpperCase()}\n\n`;
            md += `| Route | Status | Details |\n`;
            md += `|-------|--------|--------|\n`;
            
            for (const result of results) {
                const status = result.status === 'PASS' ? '✅ PASS' : 
                              result.status === 'FAIL' ? '❌ FAIL' : '⏭️ SKIP';
                const details = result.error || result.feature || '-';
                md += `| ${result.route} | ${status} | ${details} |\n`;
            }
            md += '\n';
        }
        
        if (report.errors.length > 0) {
            md += `## Errors\n\n`;
            for (const error of report.errors) {
                md += `- **${error.route}**: ${error.error}\n`;
            }
            md += '\n';
        }
        
        md += `## Screenshots\n\n`;
        md += `Total: ${report.screenshots.length} screenshots saved.\n\n`;
        md += `Location: \`${CONFIG.screenshotDir}\`\n\n`;
        
        // Group screenshots by subdirectory
        const screenshotsByDir = {};
        for (const ss of report.screenshots) {
            const dir = path.dirname(ss.path).split(path.sep).pop();
            if (!screenshotsByDir[dir]) {
                screenshotsByDir[dir] = [];
            }
            screenshotsByDir[dir].push(ss.name);
        }
        
        for (const [dir, names] of Object.entries(screenshotsByDir)) {
            md += `### ${dir}/\n`;
            for (const name of names) {
                md += `- ${name}\n`;
            }
            md += '\n';
        }
        
        return md;
    }
    
    async cleanup() {
        if (this.browser) {
            await this.browser.close();
        }
    }
}

// ============================================================================
// EXECUTION
// ============================================================================

(async () => {
    const testSuite = new ComprehensiveTestSuite();
    
    try {
        await testSuite.runAllTests();
    } catch (error) {
        console.error('\n❌ FATAL ERROR:', error.message);
        console.error(error.stack);
    } finally {
        await testSuite.cleanup();
        process.exit(0);
    }
})();
