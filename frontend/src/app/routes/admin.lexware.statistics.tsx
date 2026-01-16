/**
 * Lexware Statistiken Page
 *
 * Route fuer /admin/lexware/statistics - Verknuepfungs-Statistiken
 */

import { createFileRoute } from '@tanstack/react-router'
import { LinkingStatisticsPage } from '@/features/admin/lexware/LinkingStatisticsPage'

export const Route = createFileRoute('/admin/lexware/statistics')({
  component: LinkingStatisticsPage,
})
