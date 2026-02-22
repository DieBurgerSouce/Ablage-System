/**
 * Schritt 4: OCR-Ergebnis verstehen
 *
 * - Zeigt extrahierte Felder aus dem hochgeladenen Dokument
 * - Erklaert Konfidenz-Scores mit Farbkodierung
 * - Zeigt Korrektur-Moeglichkeit
 */

import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  FileText,
  Eye,
  Pencil,
  Check,
  Info,
  Lightbulb,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

interface UploadedDocument {
  id: string
  name: string
  ocrStatus: 'pending' | 'processing' | 'completed' | 'failed'
  ocrConfidence?: number
  extractedText?: string
}

interface ResultStepProps {
  document: UploadedDocument | null
}

interface ExtractedField {
  id: string
  label: string
  value: string
  confidence: number
  editable: boolean
}

/** Generate demo fields - in production these would come from the API */
function generateExtractedFields(doc: UploadedDocument | null): ExtractedField[] {
  if (!doc) {
    return [
      { id: 'type', label: 'Dokumenttyp', value: 'Rechnung', confidence: 92, editable: false },
      { id: 'date', label: 'Datum', value: '15.02.2026', confidence: 98, editable: true },
      { id: 'amount', label: 'Betrag', value: '1.234,56 EUR', confidence: 95, editable: true },
      { id: 'sender', label: 'Absender', value: 'Beispiel GmbH', confidence: 85, editable: true },
      { id: 'number', label: 'Rechnungsnr.', value: 'RE-2026-0042', confidence: 72, editable: true },
      { id: 'tax', label: 'MwSt.', value: '234,56 EUR', confidence: 68, editable: true },
    ]
  }

  const confidence = doc.ocrConfidence ?? 85
  return [
    { id: 'type', label: 'Dokumenttyp', value: 'Erkannt', confidence: confidence, editable: false },
    { id: 'text', label: 'Erkannter Text', value: doc.extractedText?.substring(0, 50) || 'Text wird geladen...', confidence: confidence, editable: true },
    { id: 'status', label: 'Status', value: doc.ocrStatus === 'completed' ? 'Abgeschlossen' : 'In Verarbeitung', confidence: 100, editable: false },
  ]
}

function getConfidenceColor(confidence: number): string {
  if (confidence >= 95) return 'text-green-600 bg-green-500/10 border-green-500/20'
  if (confidence >= 70) return 'text-yellow-600 bg-yellow-500/10 border-yellow-500/20'
  return 'text-red-600 bg-red-500/10 border-red-500/20'
}

function getConfidenceLabel(confidence: number): string {
  if (confidence >= 95) return 'Hoch'
  if (confidence >= 70) return 'Mittel'
  return 'Niedrig'
}

export function ResultStep({ document }: ResultStepProps) {
  const fields = generateExtractedFields(document)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editValues, setEditValues] = useState<Record<string, string>>({})
  const [correctedFields, setCorrectedFields] = useState<Set<string>>(new Set())

  const handleEdit = (fieldId: string, currentValue: string) => {
    setEditingId(fieldId)
    setEditValues((prev) => ({ ...prev, [fieldId]: currentValue }))
  }

  const handleSave = (fieldId: string) => {
    setCorrectedFields((prev) => new Set([...prev, fieldId]))
    setEditingId(null)
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="text-center pb-2">
        <div className="p-3 rounded-full bg-primary/10 border border-primary/20 inline-block mb-3">
          <Eye className="w-8 h-8 text-primary" aria-hidden="true" />
        </div>
        <h2 className="text-lg font-semibold">OCR-Ergebnis verstehen</h2>
        <p className="text-sm text-muted-foreground mt-1 max-w-md mx-auto">
          So sehen die automatisch extrahierten Felder aus. Farben zeigen die Erkennungs-Sicherheit.
        </p>
      </div>

      {/* Confidence Legend */}
      <div className="flex justify-center gap-4 text-xs">
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-green-500" />
          <span className="text-muted-foreground">&gt;95% Sicher</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-yellow-500" />
          <span className="text-muted-foreground">70-95% Pruefen</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-red-500" />
          <span className="text-muted-foreground">&lt;70% Korrigieren</span>
        </div>
      </div>

      {/* Document info */}
      {document && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground bg-muted/30 rounded-lg px-3 py-2">
          <FileText className="w-4 h-4" />
          <span>{document.name}</span>
          {document.ocrConfidence != null && (
            <Badge variant="outline" className={cn('ml-auto', getConfidenceColor(document.ocrConfidence))}>
              {document.ocrConfidence}%
            </Badge>
          )}
        </div>
      )}

      {/* Extracted fields */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center gap-2">
            <ScanIcon className="w-4 h-4" />
            Extrahierte Felder
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {fields.map((field) => {
            const isEditing = editingId === field.id
            const isCorrected = correctedFields.has(field.id)
            const displayValue = editValues[field.id] ?? field.value

            return (
              <div
                key={field.id}
                className={cn(
                  'flex items-center gap-3 p-2.5 rounded-lg border transition-colors',
                  getConfidenceColor(field.confidence),
                  isCorrected && 'border-green-500/40 bg-green-500/5',
                )}
              >
                {/* Confidence dot */}
                <div
                  className={cn(
                    'w-2 h-2 rounded-full flex-shrink-0',
                    field.confidence >= 95 ? 'bg-green-500' : field.confidence >= 70 ? 'bg-yellow-500' : 'bg-red-500',
                  )}
                  aria-label={`Konfidenz: ${field.confidence}%`}
                />

                {/* Label */}
                <Label className="text-xs font-medium w-24 flex-shrink-0">
                  {field.label}
                </Label>

                {/* Value / Edit */}
                <div className="flex-1 min-w-0">
                  {isEditing ? (
                    <div className="flex items-center gap-2">
                      <Input
                        value={editValues[field.id] ?? field.value}
                        onChange={(e) =>
                          setEditValues((prev) => ({ ...prev, [field.id]: e.target.value }))
                        }
                        className="h-7 text-xs"
                        autoFocus
                        aria-label={`${field.label} bearbeiten`}
                      />
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 w-7 p-0"
                        onClick={() => handleSave(field.id)}
                        aria-label="Korrektur speichern"
                      >
                        <Check className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <span className="text-xs truncate">{displayValue}</span>
                      {isCorrected && (
                        <Badge variant="outline" className="text-green-600 border-green-500/30 text-[10px] px-1.5 py-0">
                          Korrigiert
                        </Badge>
                      )}
                    </div>
                  )}
                </div>

                {/* Confidence & Edit button */}
                <div className="flex items-center gap-1.5 flex-shrink-0">
                  <span className="text-[10px] tabular-nums">{field.confidence}%</span>
                  {field.editable && !isEditing && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-6 w-6 p-0"
                      onClick={() => handleEdit(field.id, displayValue)}
                      aria-label={`${field.label} bearbeiten`}
                    >
                      <Pencil className="w-3 h-3" />
                    </Button>
                  )}
                </div>
              </div>
            )
          })}
        </CardContent>
      </Card>

      {/* Info about corrections */}
      <Alert>
        <Lightbulb className="h-4 w-4" aria-hidden="true" />
        <AlertDescription className="text-xs">
          <strong>Tipp:</strong> Gelbe und rote Felder koennen Sie korrigieren.
          Klicken Sie auf das Stift-Symbol. Ihre Korrekturen verbessern das System automatisch
          fuer zukuenftige Erkennungen.
        </AlertDescription>
      </Alert>
    </div>
  )
}

function ScanIcon({ className }: { className?: string }) {
  return <Eye className={className} aria-hidden="true" />
}
