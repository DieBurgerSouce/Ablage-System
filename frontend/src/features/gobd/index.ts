/**
 * GoBD Feature Module
 *
 * Exports for GoBD-compliant document archiving feature.
 */

// Types
export * from './types'

// API
export * from './api/gobd-api'

// Hooks
export * from './hooks/use-gobd'

// Components
export { ArchiveManagement } from './components/ArchiveManagement'
export { RetentionSettings } from './components/RetentionSettings'
export { ProcedureDocViewer } from './components/ProcedureDocViewer'
