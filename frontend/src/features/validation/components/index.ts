/**
 * Validation Components Exports
 */

// Legacy Components (fuer Rueckwaertskompatibilitaet)
export { ValidationDashboard } from './ValidationDashboard';
export { ValidationEditor } from './ValidationEditor';
export { ValidationCard } from './ValidationCard';
export { ValidationStats } from './ValidationStats';
export { ConfidenceIndicator } from './ConfidenceIndicator';
export * from './dialogs';

// Neue Queue-basierte Komponenten
export { ValidationQueueDashboard } from './ValidationQueueDashboard';
export { ValidationQueueEditor } from './ValidationQueueEditor';
export { ValidationPDFViewer } from './ValidationPDFViewer';

// Dialoge
export { RejectReasonDialog } from './RejectReasonDialog';
export { AssignEditorDialog } from './AssignEditorDialog';
export { BulkApproveDialog } from './BulkApproveDialog';

// Rules & Config
export { RulesManager } from './RulesManager';
export { RuleFormDialog } from './RuleFormDialog';
export { SampleConfigDialog } from './SampleConfigDialog';

// Analytics
export { AnalyticsDashboard } from './AnalyticsDashboard';

// Quick Validation (Mobile + Keyboard Support)
export { QuickValidationCard, QuickValidationList } from './QuickValidationCard';
