/**
 * Workflow Versioning Route
 *
 * Route: /workflows/:workflowId/versions
 *
 * Features:
 * - Versions-Liste mit Semantic Versioning
 * - Diff-Ansicht zwischen Versionen
 * - A/B Testing UI
 * - One-Click Rollback
 * - Version-Status (Draft, Active, Deprecated)
 */

import { createFileRoute } from '@tanstack/react-router';
import { WorkflowVersionsPage } from '@/features/workflows/versioning/WorkflowVersionsPage';

export const Route = createFileRoute('/workflows/$workflowId/versions')({
  component: WorkflowVersionsPage,
});
