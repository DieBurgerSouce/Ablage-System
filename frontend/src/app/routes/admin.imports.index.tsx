/**
 * Admin Imports Index Route
 *
 * Haupt-Import-Verwaltungsseite mit Uebersicht ueber alle Konfigurationen.
 */

import { createFileRoute } from '@tanstack/react-router'
import { ImportsPage } from '@/features/imports'

export const Route = createFileRoute('/admin/imports/')({
  component: AdminImportsPage,
})

function AdminImportsPage() {
  return <ImportsPage />
}
