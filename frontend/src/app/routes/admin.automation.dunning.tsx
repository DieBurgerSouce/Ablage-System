/**
 * Dunning Config Route
 * Route für Mahnung-Automatisierung Konfiguration
 */

import { createFileRoute } from '@tanstack/react-router'
import { DunningConfigPage } from '@/features/admin/automation/DunningConfigPage'

export const Route = createFileRoute('/admin/automation/dunning')({
  component: DunningConfigPage,
})
