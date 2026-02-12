/**
 * Action Approval Queue Route
 * Route für Aktions-Warteschlange
 */

import { createFileRoute } from '@tanstack/react-router'
import { ActionApprovalQueue } from '@/features/admin/automation/ActionApprovalQueue'

export const Route = createFileRoute('/admin/automation/queue')({
  component: ActionApprovalQueue,
})
