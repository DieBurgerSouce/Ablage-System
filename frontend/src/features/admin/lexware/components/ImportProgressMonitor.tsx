/**
 * ImportProgressMonitor - Fortschrittsanzeige für Lexware Import
 *
 * WICHTIG: Types müssen EXAKT mit Backend übereinstimmen!
 * Backend verwendet snake_case: imported_count, updated_count, etc.
 * @see app/api/v1/lexware.py:LexwareImportResponse
 *
 * Features:
 * - Progress-Bar mit Prozentanzeige
 * - Erfolge/Fehler-Counter (snake_case!)
 * - Message vom Backend
 * - Dry-Run Hinweis
 */

import { useMemo } from 'react'
import {
  CheckCircle,
  XCircle,
  AlertTriangle,
  Loader2,
  RefreshCw,
  SkipForward,
  Plus,
  FlaskConical,
} from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import type { LexwareImportResponse } from '../api/lexware-admin-api'

interface ImportProgressMonitorProps {
  status: 'idle' | 'importing' | 'success' | 'error'
  importResult: LexwareImportResponse | null
  errorMessage?: string
  isDryRun?: boolean
}

export function ImportProgressMonitor({
  status,
  importResult,
  errorMessage,
  isDryRun = false,
}: ImportProgressMonitorProps) {
  // Calculate stats from snake_case backend response
  const stats = useMemo(() => {
    if (!importResult) {
      return { total: 0, imported: 0, updated: 0, skipped: 0, errors: 0, progress: 0 }
    }

    const total =
      importResult.imported_count +
      importResult.updated_count +
      importResult.skipped_count +
      importResult.error_count
    const progress = total > 0 ? 100 : 0

    return {
      total,
      imported: importResult.imported_count,
      updated: importResult.updated_count,
      skipped: importResult.skipped_count,
      errors: importResult.error_count,
      progress,
    }
  }, [importResult])

  // Importing State
  if (status === 'importing') {
    return (
      <Card>
        <CardContent className="py-12">
          <div className="flex flex-col items-center gap-4">
            <Loader2 className="h-12 w-12 animate-spin text-primary" />
            <p className="text-lg font-medium">
              {isDryRun ? 'Testlauf wird durchgeführt...' : 'Daten werden importiert...'}
            </p>
            <p className="text-muted-foreground">
              Bitte warten Sie, dies kann einen Moment dauern.
            </p>
            <Progress value={undefined} className="w-64" />
          </div>
        </CardContent>
      </Card>
    )
  }

  // Error State
  if (status === 'error') {
    return (
      <Card className="border-red-200 dark:border-red-800">
        <CardContent className="py-8">
          <div className="flex flex-col items-center gap-4">
            <div className="p-3 bg-red-100 dark:bg-red-900 rounded-full">
              <XCircle className="h-10 w-10 text-red-600 dark:text-red-400" />
            </div>
            <p className="text-lg font-medium text-red-700 dark:text-red-300">
              Import fehlgeschlagen
            </p>
            <p className="text-muted-foreground text-center max-w-md">
              {errorMessage || 'Ein unbekannter Fehler ist aufgetreten.'}
            </p>
          </div>
        </CardContent>
      </Card>
    )
  }

  // Idle State (no result yet)
  if (status === 'idle' || !importResult) {
    return null
  }

  // Success State with Results
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {isDryRun ? (
            <>
              <FlaskConical className="h-5 w-5 text-blue-500" />
              Testlauf abgeschlossen
            </>
          ) : (
            <>
              <CheckCircle className="h-5 w-5 text-green-500" />
              Import abgeschlossen
            </>
          )}
        </CardTitle>
        <CardDescription>
          {stats.total} Datensätze verarbeitet
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Dry Run Alert */}
        {isDryRun && (
          <Alert>
            <FlaskConical className="h-4 w-4" />
            <AlertTitle>Testmodus</AlertTitle>
            <AlertDescription>
              Dies war ein Testlauf. Es wurden keine Änderungen in der Datenbank gespeichert.
              Deaktivieren Sie den Testmodus, um den Import durchzuführen.
            </AlertDescription>
          </Alert>
        )}

        {/* Progress Bar */}
        <Progress value={stats.progress} className="h-3" />

        {/* Stats Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            icon={Plus}
            label="Importiert"
            value={stats.imported}
            variant="success"
          />
          <StatCard
            icon={RefreshCw}
            label="Aktualisiert"
            value={stats.updated}
            variant="info"
          />
          <StatCard
            icon={SkipForward}
            label="Übersprungen"
            value={stats.skipped}
            variant="warning"
          />
          <StatCard
            icon={XCircle}
            label="Fehler"
            value={stats.errors}
            variant="error"
          />
        </div>

        {/* Backend Message */}
        {importResult.message && (
          <div className="p-3 bg-muted/50 rounded-lg">
            <p className="text-sm">{importResult.message}</p>
          </div>
        )}

        {/* Conflicts Summary */}
        {importResult.conflicts.length > 0 && (
          <div className="p-3 bg-yellow-50 dark:bg-yellow-950/20 border border-yellow-200 dark:border-yellow-800 rounded-lg">
            <div className="flex items-center gap-2 text-yellow-700 dark:text-yellow-300">
              <AlertTriangle className="h-4 w-4" />
              <span className="font-medium">
                {importResult.conflicts.length} Konflikte zwischen Folie und Messer
              </span>
            </div>
            <p className="text-sm text-yellow-600 dark:text-yellow-400 mt-1">
              Kritische Konflikte wurden übersprungen. Prüfen Sie die Lexware-Exporte auf Konsistenz.
            </p>
          </div>
        )}

        {/* Task ID for async operations */}
        {importResult.task_id && (
          <p className="text-xs text-muted-foreground">
            Task-ID: {importResult.task_id}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function StatCard({
  icon: Icon,
  label,
  value,
  variant,
}: {
  icon: React.ElementType
  label: string
  value: number
  variant: 'success' | 'info' | 'warning' | 'error'
}) {
  const variantStyles = {
    success: 'bg-green-50 text-green-700 dark:bg-green-950/30 dark:text-green-300',
    info: 'bg-blue-50 text-blue-700 dark:bg-blue-950/30 dark:text-blue-300',
    warning: 'bg-yellow-50 text-yellow-700 dark:bg-yellow-950/30 dark:text-yellow-300',
    error: 'bg-red-50 text-red-700 dark:bg-red-950/30 dark:text-red-300',
  }

  const iconStyles = {
    success: 'text-green-500',
    info: 'text-blue-500',
    warning: 'text-yellow-500',
    error: 'text-red-500',
  }

  return (
    <div className={`p-4 rounded-lg ${variantStyles[variant]}`}>
      <div className="flex items-center gap-2 mb-1">
        <Icon className={`h-4 w-4 ${iconStyles[variant]}`} />
        <span className="text-sm">{label}</span>
      </div>
      <span className="text-2xl font-bold">{value}</span>
    </div>
  )
}
