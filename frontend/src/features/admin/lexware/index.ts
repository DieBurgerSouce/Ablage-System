/**
 * Lexware Admin Feature - Exports
 *
 * WICHTIG: Alle Komponenten verwenden Types die EXAKT mit Backend uebereinstimmen!
 * Backend: app/api/v1/lexware.py
 * - snake_case fuer alle Response-Felder
 * - Zwei Dateien (folie_file + messer_file) fuer Import
 * - ConflictInfo mit conflict_type: 'critical' | 'harmless' | 'duplicate'
 */

// Pages
export { LexwareImportPage } from './LexwareImportPage'
export { LinkingStatisticsPage } from './LinkingStatisticsPage'

// Components
export { ImportUploadZone } from './components/ImportUploadZone'
export { ImportConflictPreview } from './components/ImportConflictPreview'
export { ImportProgressMonitor } from './components/ImportProgressMonitor'
export { LinkingStatisticsCard } from './components/LinkingStatisticsCard'

// API
export * from './api/lexware-admin-api'
