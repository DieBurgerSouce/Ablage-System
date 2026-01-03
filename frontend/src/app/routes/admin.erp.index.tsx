/**
 * ERP Connections Index Route
 *
 * Hauptseite fuer ERP-Verbindungsverwaltung.
 */

import { createFileRoute } from '@tanstack/react-router'
import { ERPConnectionsPage } from '@/features/erp'

export const Route = createFileRoute('/admin/erp/')({
  component: ERPConnectionsPage,
})
