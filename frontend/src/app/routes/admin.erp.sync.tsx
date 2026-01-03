/**
 * ERP Sync Dashboard Route
 *
 * Sync-Status und Historie.
 */

import { createFileRoute } from '@tanstack/react-router'
import { SyncDashboard } from '@/features/erp'

export const Route = createFileRoute('/admin/erp/sync')({
  component: SyncDashboard,
})
