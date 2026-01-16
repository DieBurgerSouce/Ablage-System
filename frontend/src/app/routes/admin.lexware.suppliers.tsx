/**
 * Lexware Lieferanten-Import Page
 *
 * Route fuer /admin/lexware/suppliers - Lieferanten importieren
 */

import { createFileRoute } from '@tanstack/react-router'
import { LexwareImportPage } from '@/features/admin/lexware/LexwareImportPage'

export const Route = createFileRoute('/admin/lexware/suppliers')({
  component: LexwareSupplierImportRoute,
})

function LexwareSupplierImportRoute() {
  return <LexwareImportPage entityType="supplier" />
}
