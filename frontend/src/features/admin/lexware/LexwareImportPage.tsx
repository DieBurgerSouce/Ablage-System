/**
 * LexwareImportPage - Hauptseite für Lexware Excel-Import
 *
 * WICHTIG: Backend erwartet ZWEI Dateien gleichzeitig (Folie + Messer)!
 *
 * Multi-Step Wizard:
 * 1. Beide Dateien hochladen (Folie + Messer)
 * 2. Konflikte prüfen (falls vorhanden)
 * 3. Import durchführen
 * 4. Ergebnis anzeigen
 */

import { useState, useCallback } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Users, Package } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { useToast } from '@/components/ui/use-toast'
import { ImportUploadZone } from './components/ImportUploadZone'
import { ImportConflictPreview } from './components/ImportConflictPreview'
import { ImportProgressMonitor } from './components/ImportProgressMonitor'
import {
  importCustomers,
  importSuppliers,
  type EntityType,
  type LexwareImportResponse,
} from './api/lexware-admin-api'

type ImportStep = 'upload' | 'conflicts' | 'importing' | 'result'

interface LexwareImportPageProps {
  entityType: EntityType
}

export function LexwareImportPage({ entityType }: LexwareImportPageProps) {
  const { toast } = useToast()
  const queryClient = useQueryClient()

  // State - ZWEI Dateien (Folie + Messer)
  const [step, setStep] = useState<ImportStep>('upload')
  const [folieFile, setFolieFile] = useState<File | null>(null)
  const [messerFile, setMesserFile] = useState<File | null>(null)
  const [skipConflicts, setSkipConflicts] = useState(true)
  const [dryRun, setDryRun] = useState(false)
  const [importResult, setImportResult] = useState<LexwareImportResponse | null>(null)

  // Both files selected?
  const bothFilesSelected = folieFile !== null && messerFile !== null

  // Import Mutation
  const importMutation = useMutation({
    mutationFn: async () => {
      if (!folieFile || !messerFile) {
        throw new Error('Beide Dateien (Folie + Messer) müssen ausgewählt sein')
      }

      const importFn = entityType === 'customer' ? importCustomers : importSuppliers
      return importFn(folieFile, messerFile, skipConflicts, dryRun)
    },
    onSuccess: (result) => {
      setImportResult(result)

      // Check if there are critical conflicts
      const hasCriticalConflicts = result.conflicts.some(c => c.conflict_type === 'critical')

      if (hasCriticalConflicts && !skipConflicts) {
        setStep('conflicts')
      } else {
        setStep('result')
        // Invalidate entity queries to refresh data
        queryClient.invalidateQueries({
          queryKey: [entityType === 'customer' ? 'customers' : 'suppliers']
        })
      }

      // Show toast for dry run
      if (dryRun) {
        toast({
          title: 'Testlauf abgeschlossen',
          description: 'Keine Änderungen wurden gespeichert. Deaktivieren Sie den Testmodus für den echten Import.',
        })
      }
    },
    onError: (error) => {
      toast({
        title: 'Import fehlgeschlagen',
        description: error instanceof Error ? error.message : 'Ein unbekannter Fehler ist aufgetreten',
        variant: 'destructive',
      })
      setStep('result')
    },
  })

  // Handlers
  const handleStartImport = useCallback(() => {
    setStep('importing')
    importMutation.mutate()
  }, [importMutation])

  const handleReset = useCallback(() => {
    setFolieFile(null)
    setMesserFile(null)
    setImportResult(null)
    setStep('upload')
  }, [])

  const entityLabel = entityType === 'customer' ? 'Kunden' : 'Lieferanten'
  const EntityIcon = entityType === 'customer' ? Users : Package

  return (
    <div className="space-y-6">
      {/* Step Indicator */}
      <div className="flex items-center gap-2 text-sm">
        <StepIndicator step={1} label="Dateien wählen" active={step === 'upload'} />
        <ArrowRight className="h-4 w-4 text-muted-foreground" />
        <StepIndicator step={2} label="Konflikte prüfen" active={step === 'conflicts'} />
        <ArrowRight className="h-4 w-4 text-muted-foreground" />
        <StepIndicator step={3} label="Ergebnis" active={step === 'result' || step === 'importing'} />
      </div>

      {/* Step: Upload */}
      {step === 'upload' && (
        <div className="space-y-6">
          {/* Upload Zone - Dual File Upload */}
          <ImportUploadZone
            folieFile={folieFile}
            messerFile={messerFile}
            onFolieFileSelect={setFolieFile}
            onMesserFileSelect={setMesserFile}
            entityType={entityType}
            isDisabled={importMutation.isPending}
          />

          {/* Settings Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <EntityIcon className="h-5 w-5" />
                Import-Einstellungen
              </CardTitle>
              <CardDescription>
                Optionen für den {entityLabel}-Import
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Skip Conflicts Toggle */}
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label htmlFor="skip-conflicts">Konflikte überspringen</Label>
                  <p className="text-sm text-muted-foreground">
                    Datensätze mit kritischen Konflikten werden übersprungen
                  </p>
                </div>
                <Switch
                  id="skip-conflicts"
                  checked={skipConflicts}
                  onCheckedChange={setSkipConflicts}
                />
              </div>

              {/* Dry Run Toggle */}
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label htmlFor="dry-run">Testmodus (Dry Run)</Label>
                  <p className="text-sm text-muted-foreground">
                    Prüft den Import ohne Änderungen zu speichern
                  </p>
                </div>
                <Switch
                  id="dry-run"
                  checked={dryRun}
                  onCheckedChange={setDryRun}
                />
              </div>

              {/* Actions */}
              <div className="flex justify-end pt-4">
                <Button
                  onClick={handleStartImport}
                  disabled={!bothFilesSelected || importMutation.isPending}
                  size="lg"
                >
                  {dryRun ? 'Testlauf starten' : 'Import starten'}
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Step: Conflicts */}
      {step === 'conflicts' && importResult && (
        <div className="space-y-6">
          <ImportConflictPreview conflicts={importResult.conflicts} />

          <div className="flex justify-between">
            <Button variant="outline" onClick={() => setStep('upload')}>
              Zurück
            </Button>
            <Button onClick={() => {
              setSkipConflicts(true)
              setStep('importing')
              importMutation.mutate()
            }}>
              Konflikte überspringen und fortfahren
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Step: Importing / Result */}
      {(step === 'importing' || step === 'result') && (
        <div className="space-y-6">
          <ImportProgressMonitor
            status={
              importMutation.isPending
                ? 'importing'
                : importMutation.isError
                ? 'error'
                : importResult
                ? 'success'
                : 'idle'
            }
            importResult={importResult}
            errorMessage={
              importMutation.error instanceof Error
                ? importMutation.error.message
                : undefined
            }
            isDryRun={dryRun}
          />

          {step === 'result' && (
            <div className="flex justify-center">
              <Button onClick={handleReset}>
                Weiteren Import durchführen
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function StepIndicator({
  step,
  label,
  active,
}: {
  step: number
  label: string
  active: boolean
}) {
  return (
    <span
      className={`flex items-center gap-1 ${
        active ? 'text-primary font-medium' : 'text-muted-foreground'
      }`}
    >
      <span
        className={`flex items-center justify-center w-6 h-6 rounded-full text-xs ${
          active
            ? 'bg-primary text-primary-foreground'
            : 'bg-muted text-muted-foreground'
        }`}
      >
        {step}
      </span>
      {label}
    </span>
  )
}
