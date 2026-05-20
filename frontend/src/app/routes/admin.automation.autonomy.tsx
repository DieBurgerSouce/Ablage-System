/**
 * Autonomy Config Route
 * Route für KI-Autonomie Konfiguration
 */

import { createFileRoute } from '@tanstack/react-router'
import { AutonomyConfigPage } from '@/features/admin/automation/AutonomyConfigPage'

export const Route = createFileRoute('/admin/automation/autonomy')({
  component: AutonomyConfigPage,
})
