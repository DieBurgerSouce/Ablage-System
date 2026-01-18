/**
 * Templates Feature - Dokumenten-Vorlagen
 *
 * Dokumentvorlagen-Verwaltung mit:
 * - Jinja2-Template-Syntax
 * - Variablen-Definition
 * - PDF/HTML/DOCX Generierung
 * - Versionierung
 * - Textbausteine (Snippets)
 */

// Pages
export { TemplatesPage } from './pages/TemplatesPage';

// Components
export { TemplateTable } from './components/TemplateTable';
export { TemplateFilters } from './components/TemplateFilters';
export { CategoryStatsCards } from './components/CategoryStatsCards';
export { TemplateFormDialog } from './components/TemplateFormDialog';
export { TemplateDetailSheet } from './components/TemplateDetailSheet';
export { GenerateDocumentDialog } from './components/GenerateDocumentDialog';

// API
export * from './api/templates-api';

// Types
export * from './types/template-types';
