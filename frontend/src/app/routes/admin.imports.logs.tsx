/**
 * Admin Import Logs Route
 *
 * Protokoll aller Import-Aktivitäten.
 */

import { createFileRoute } from '@tanstack/react-router'
import { FileText } from 'lucide-react'
import { ImportLogTable } from '@/features/imports'

export const Route = createFileRoute('/admin/imports/logs')({
  component: AdminImportLogsPage,
})

function AdminImportLogsPage() {
  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center gap-3">
        <FileText className="h-8 w-8 text-primary" />
        <div>
          <h1 className="text-3xl font-bold">Import-Protokoll</h1>
          <p className="text-muted-foreground">
            Übersicht über alle Import-Aktivitäten mit Fehleranalyse und Retry-Funktionen.
          </p>
        </div>
      </div>

      <ImportLogTable maxItems={100} />
    </div>
  )
}
