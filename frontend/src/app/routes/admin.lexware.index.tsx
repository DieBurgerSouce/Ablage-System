/**
 * Lexware Kunden-Import Page
 *
 * Index-Route für /admin/lexware - Kunden importieren
 */

import { createFileRoute } from '@tanstack/react-router'
import { LexwareImportPage } from '@/features/admin/lexware/LexwareImportPage'

export const Route = createFileRoute('/admin/lexware/')({
  component: LexwareCustomerImportRoute,
})

function LexwareCustomerImportRoute() {
  return <LexwareImportPage entityType="customer" />
}
