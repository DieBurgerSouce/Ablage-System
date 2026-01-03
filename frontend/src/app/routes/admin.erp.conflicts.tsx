/**
 * ERP Conflict Resolver Route
 *
 * Konflikt-Aufloesung UI.
 */

import { createFileRoute } from '@tanstack/react-router'
import { ConflictResolver } from '@/features/erp'

export const Route = createFileRoute('/admin/erp/conflicts')({
  component: ConflictResolver,
})
