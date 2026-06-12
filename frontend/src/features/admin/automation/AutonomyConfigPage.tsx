/**
 * Autonomy Config Page
 * Admin-Seite für KI-Autonomie Konfiguration
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Save, RotateCcw, Settings, Sliders, Loader2, CheckCircle2, Clock, AlertCircle } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'
import { getAutonomyConfig, updateAutonomyConfig } from './api/automation-config-api'
import type { AutonomyConfig } from './api/automation-config-api'

// German labels for action types
const ACTION_TYPE_LABELS: Record<string, string> = {
  FILE_DOCUMENT: 'Ablegen',
  APPROVE_PAYMENT: 'Zahlung freigeben',
  SEND_DUNNING: 'Mahnung senden',
  UPDATE_MASTER_DATA: 'Stammdaten aktualisieren',
  ASSIGN_ENTITY: 'Entität zuweisen',
  CLASSIFY_DOCUMENT: 'Klassifizieren',
}

// Trust level labels and colors
const TRUST_LEVEL_INFO = {
  immediate: { label: 'Sofort', color: 'bg-green-500' },
  delayed: { label: 'Verzögert', color: 'bg-yellow-500' },
  confirm: { label: 'Bestätigung', color: 'bg-red-500' },
}

export function AutonomyConfigPage() {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [formData, setFormData] = useState<AutonomyConfig | null>(null)

  // Load config
  const { data: config, isLoading } = useQuery({
    queryKey: ['autonomy-config'],
    queryFn: getAutonomyConfig,
    onSuccess: (data) => setFormData(data),
  })

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: updateAutonomyConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['autonomy-config'] })
      toast({
        title: 'Gespeichert',
        description: 'Autonomie-Konfiguration wurde erfolgreich aktualisiert',
      })
    },
    onError: () => {
      toast({
        title: 'Fehler',
        description: 'Konfiguration konnte nicht gespeichert werden',
        variant: 'destructive',
      })
    },
  })

  const handleSave = () => {
    if (formData) {
      updateMutation.mutate(formData)
    }
  }

  const handleReset = () => {
    if (config) {
      setFormData(config)
    }
  }

  const handleThresholdChange = (field: keyof AutonomyConfig, value: number) => {
    if (formData) {
      setFormData({ ...formData, [field]: value })
    }
  }

  const handleTrustLevelChange = (actionType: string, trustLevel: 'immediate' | 'delayed' | 'confirm') => {
    if (!formData) return

    const updatedTrustLevels = formData.action_trust_levels.map((level) =>
      level.action_type === actionType ? { ...level, trust_level: trustLevel } : level
    )

    setFormData({ ...formData, action_trust_levels: updatedTrustLevels })
  }

  if (isLoading || !formData) {
    return (
      <div className="container mx-auto py-6">
        <div className="flex items-center justify-center min-h-[400px]">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Settings className="h-6 w-6" />
            Autonomie-Konfiguration
          </h1>
          <p className="text-muted-foreground">
            Konfigurieren Sie die Vertrauensstufen für automatische Aktionen
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleReset} disabled={updateMutation.isPending}>
            <RotateCcw className="h-4 w-4 mr-2" />
            Zurücksetzen
          </Button>
          <Button onClick={handleSave} disabled={updateMutation.isPending}>
            {updateMutation.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Save className="h-4 w-4 mr-2" />
            )}
            Speichern
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Thresholds */}
        <div className="lg:col-span-2 space-y-6">
          {/* Konfidenz-Schwellenwerte */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Sliders className="h-5 w-5" />
                Konfidenz-Schwellenwerte
              </CardTitle>
              <CardDescription>
                Legen Sie die minimale Konfidenz für automatische Aktionen fest (0.00 - 1.00)
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="document_classification_threshold">Dokumentenklassifikation</Label>
                  <Input
                    id="document_classification_threshold"
                    type="number"
                    step="0.01"
                    min={0}
                    max={1}
                    value={formData.document_classification_threshold}
                    onChange={(e) =>
                      handleThresholdChange('document_classification_threshold', parseFloat(e.target.value) || 0)
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="entity_linking_threshold">Entitätszuordnung</Label>
                  <Input
                    id="entity_linking_threshold"
                    type="number"
                    step="0.01"
                    min={0}
                    max={1}
                    value={formData.entity_linking_threshold}
                    onChange={(e) => handleThresholdChange('entity_linking_threshold', parseFloat(e.target.value) || 0)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="invoice_approval_threshold">Rechnungsfreigabe</Label>
                  <Input
                    id="invoice_approval_threshold"
                    type="number"
                    step="0.01"
                    min={0}
                    max={1}
                    value={formData.invoice_approval_threshold}
                    onChange={(e) =>
                      handleThresholdChange('invoice_approval_threshold', parseFloat(e.target.value) || 0)
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="payment_matching_threshold">Zahlungszuordnung</Label>
                  <Input
                    id="payment_matching_threshold"
                    type="number"
                    step="0.01"
                    min={0}
                    max={1}
                    value={formData.payment_matching_threshold}
                    onChange={(e) =>
                      handleThresholdChange('payment_matching_threshold', parseFloat(e.target.value) || 0)
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="ocr_correction_threshold">OCR-Korrektur</Label>
                  <Input
                    id="ocr_correction_threshold"
                    type="number"
                    step="0.01"
                    min={0}
                    max={1}
                    value={formData.ocr_correction_threshold}
                    onChange={(e) => handleThresholdChange('ocr_correction_threshold', parseFloat(e.target.value) || 0)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="master_data_auto_update_confidence">Stammdaten-Update</Label>
                  <Input
                    id="master_data_auto_update_confidence"
                    type="number"
                    step="0.01"
                    min={0}
                    max={1}
                    value={formData.master_data_auto_update_confidence}
                    onChange={(e) =>
                      handleThresholdChange('master_data_auto_update_confidence', parseFloat(e.target.value) || 0)
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="filing_auto_confidence">Automatische Ablage</Label>
                  <Input
                    id="filing_auto_confidence"
                    type="number"
                    step="0.01"
                    min={0}
                    max={1}
                    value={formData.filing_auto_confidence}
                    onChange={(e) => handleThresholdChange('filing_auto_confidence', parseFloat(e.target.value) || 0)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="filing_suggest_confidence">Ablage-Vorschlag</Label>
                  <Input
                    id="filing_suggest_confidence"
                    type="number"
                    step="0.01"
                    min={0}
                    max={1}
                    value={formData.filing_suggest_confidence}
                    onChange={(e) =>
                      handleThresholdChange('filing_suggest_confidence', parseFloat(e.target.value) || 0)
                    }
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Grenzwerte */}
          <Card>
            <CardHeader>
              <CardTitle>Grenzwerte</CardTitle>
              <CardDescription>Betragsgrenzen und Eskalationsregeln</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="payment_auto_approve_limit">Automatische Zahlungsfreigabe bis (EUR)</Label>
                  <Input
                    id="payment_auto_approve_limit"
                    type="number"
                    step="0.01"
                    min={0}
                    value={formData.payment_auto_approve_limit}
                    onChange={(e) =>
                      handleThresholdChange('payment_auto_approve_limit', parseFloat(e.target.value) || 0)
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="payment_suggest_limit">Zahlungsvorschlag bis (EUR)</Label>
                  <Input
                    id="payment_suggest_limit"
                    type="number"
                    step="0.01"
                    min={0}
                    value={formData.payment_suggest_limit}
                    onChange={(e) => handleThresholdChange('payment_suggest_limit', parseFloat(e.target.value) || 0)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="dunning_auto_send_level">Automatische Mahnstufe</Label>
                  <Input
                    id="dunning_auto_send_level"
                    type="number"
                    min={0}
                    max={3}
                    value={formData.dunning_auto_send_level}
                    onChange={(e) => handleThresholdChange('dunning_auto_send_level', parseInt(e.target.value) || 0)}
                  />
                  <p className="text-xs text-muted-foreground">0 = Keine, 1 = Erste Mahnung, 2 = Zweite Mahnung, 3 = Letzte Mahnung</p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="dunning_min_overdue_days">Mindest-Überfälligkeitstage</Label>
                  <Input
                    id="dunning_min_overdue_days"
                    type="number"
                    min={0}
                    value={formData.dunning_min_overdue_days}
                    onChange={(e) =>
                      handleThresholdChange('dunning_min_overdue_days', parseInt(e.target.value) || 0)
                    }
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Vertrauensstufen pro Aktion */}
          <Card>
            <CardHeader>
              <CardTitle>Vertrauensstufen pro Aktion</CardTitle>
              <CardDescription>
                Definieren Sie, wie jede Aktion ausgeführt werden soll
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {formData.action_trust_levels.map((level) => (
                  <div key={level.action_type} className="flex items-center justify-between p-3 rounded-lg border">
                    <div className="flex items-center gap-3">
                      <div
                        className={`w-2 h-2 rounded-full ${TRUST_LEVEL_INFO[level.trust_level].color}`}
                        aria-hidden="true"
                      />
                      <span className="font-medium">{ACTION_TYPE_LABELS[level.action_type] || level.action_type}</span>
                    </div>
                    <Select
                      value={level.trust_level}
                      onValueChange={(value) =>
                        handleTrustLevelChange(level.action_type, value as 'immediate' | 'delayed' | 'confirm')
                      }
                    >
                      <SelectTrigger className="w-[180px]">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="immediate">
                          <div className="flex items-center gap-2">
                            <CheckCircle2 className="h-4 w-4 text-green-500" />
                            Sofort
                          </div>
                        </SelectItem>
                        <SelectItem value="delayed">
                          <div className="flex items-center gap-2">
                            <Clock className="h-4 w-4 text-yellow-500" />
                            Verzögert
                          </div>
                        </SelectItem>
                        <SelectItem value="confirm">
                          <div className="flex items-center gap-2">
                            <AlertCircle className="h-4 w-4 text-red-500" />
                            Bestätigung
                          </div>
                        </SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Info */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Vertrauensstufen</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-3">
                <div className="flex items-start gap-3">
                  <CheckCircle2 className="h-5 w-5 text-green-500 mt-0.5 flex-shrink-0" />
                  <div>
                    <div className="font-medium">Sofort</div>
                    <p className="text-sm text-muted-foreground">
                      Die Aktion wird sofort ausgeführt, wenn die Konfidenz hoch genug ist
                    </p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <Clock className="h-5 w-5 text-yellow-500 mt-0.5 flex-shrink-0" />
                  <div>
                    <div className="font-medium">Verzögert</div>
                    <p className="text-sm text-muted-foreground">
                      Die Aktion wird in die Warteschlange gestellt und nach einer Verzögerung ausgeführt
                    </p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <AlertCircle className="h-5 w-5 text-red-500 mt-0.5 flex-shrink-0" />
                  <div>
                    <div className="font-medium">Bestätigung</div>
                    <p className="text-sm text-muted-foreground">
                      Die Aktion erfordert manuelle Bestätigung durch einen Administrator
                    </p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Hinweise</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div>
                <strong>Konfidenz-Schwellenwerte:</strong>
                <p className="text-muted-foreground mt-1">
                  Werte zwischen 0.00 (0%) und 1.00 (100%). Aktionen werden nur ausgeführt, wenn die KI-Konfidenz über dem Schwellenwert liegt.
                </p>
              </div>
              <div>
                <strong>Empfohlene Einstellungen:</strong>
                <ul className="list-disc list-inside mt-1 text-muted-foreground">
                  <li>Kritische Aktionen: &gt;0.90</li>
                  <li>Mittlere Risiken: &gt;0.80</li>
                  <li>Niedrige Risiken: &gt;0.70</li>
                </ul>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
