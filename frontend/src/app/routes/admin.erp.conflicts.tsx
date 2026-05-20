/**
 * ERP Conflict Resolver Route
 *
 * Konflikt-Auflösung UI.
 */

import { createFileRoute } from '@tanstack/react-router'
import { ConflictResolver } from '@/features/erp'

export const Route = createFileRoute('/admin/erp/conflicts')({
  component: ConflictResolver,
})
