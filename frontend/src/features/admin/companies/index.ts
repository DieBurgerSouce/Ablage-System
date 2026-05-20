/**
 * Company Admin Feature - Multi-Mandanten-Verwaltung
 *
 * Firmenverwaltung mit:
 * - Firmen-CRUD
 * - Benutzer-Zuordnung
 * - Berechtigungsverwaltung
 * - Multi-Tenant Support für 20+ Mandanten
 */

// Pages
export { CompanyAdminPage } from './CompanyAdminPage';
export { CompanyDashboardPage } from './CompanyDashboardPage';

// Components
export { CompanyTable } from './components/CompanyTable';
export { CompanyFormDialog } from './components/CompanyFormDialog';
export { CompanyUsersDialog } from './components/CompanyUsersDialog';

// API
export * from './api/companies-admin-api';
