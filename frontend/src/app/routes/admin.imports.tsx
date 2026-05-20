/**
 * Admin Imports Layout Route
 *
 * Layout für alle Import-bezogenen Admin-Routen.
 */

import { createFileRoute, Outlet } from '@tanstack/react-router'

export const Route = createFileRoute('/admin/imports')({
  component: AdminImportsLayout,
})

function AdminImportsLayout() {
  return <Outlet />
}
