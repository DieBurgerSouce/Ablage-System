/**
 * Lexware Admin Feature - Exports
 *
 * WICHTIG: Alle Komponenten verwenden Types die EXAKT mit Backend übereinstimmen!
 * Backend: app/api/v1/lexware.py
 * - snake_case für alle Response-Felder
 * - Zwei Dateien (folie_file + messer_file) für Import
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
