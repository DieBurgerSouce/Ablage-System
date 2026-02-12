/**
 * Dunning Config Page
 * Admin-Seite für Mahnung-Automatisierung Konfiguration
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Save, RotateCcw, AlertTriangle, Clock, Euro, Loader2, CheckCircle2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { useToast } from '@/hooks/use-toast'
import { getDunningConfig, updateDunningConfig, getDunningStats } from './api/automation-config-api'
import type { DunningConfig } from './api/automation-config-api'

export function DunningConfigPage() {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [formData, setFormData] = useState<DunningConfig | null>(null)

  // Load config
  const { data: config, isLoading: isLoadingConfig } = useQuery({
    queryKey: ['dunning-config'],
    queryFn: getDunningConfig,
    onSuccess: (data) => setFormData(data),
  })

  // Load stats
  const { data: stats, isLoading: isLoadingStats } = useQuery({
    queryKey: ['dunning-stats'],
    queryFn: getDunningStats,
    refetchInterval: 30000, // Refresh every 30s
  })

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: updateDunningConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dunning-config'] })
      toast({
        title: 'Gespeichert',
        description: 'Mahnung-Konfiguration wurde erfolgreich aktualisiert',
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

  const handleChange = (field: keyof DunningConfig, value: number | boolean) => {
    if (formData) {
      setFormData({ ...formData, [field]: value })
    }
  }

  if (isLoadingConfig || !formData) {
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
            <AlertTriangle className="h-6 w-6" />
            Mahnung-Konfiguration
          </h1>
          <p className="text-muted-foreground">
            Konfigurieren Sie die automatische Mahnungsverarbeitung
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
        {/* Left Column: Configuration */}
        <div className="lg:col-span-2 space-y-6">
          {/* Zeitliche Eskalation */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Clock className="h-5 w-5" />
                Zeitliche Eskalation
              </CardTitle>
              <CardDescription>
                Definieren Sie die Zeitabstände zwischen den Mahnstufen
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="reminder_after_days">Zahlungserinnerung nach (Tagen)</Label>
                  <Input
                    id="reminder_after_days"
                    type="number"
                    min={0}
                    value={formData.reminder_after_days}
                    onChange={(e) => handleChange('reminder_after_days', parseInt(e.target.value) || 0)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="first_dunning_after_days">1. Mahnung nach (Tagen)</Label>
                  <Input
                    id="first_dunning_after_days"
                    type="number"
                    min={0}
                    value={formData.first_dunning_after_days}
                    onChange={(e) => handleChange('first_dunning_after_days', parseInt(e.target.value) || 0)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="second_dunning_after_days">2. Mahnung nach (Tagen)</Label>
                  <Input
                    id="second_dunning_after_days"
                    type="number"
                    min={0}
                    value={formData.second_dunning_after_days}
                    onChange={(e) => handleChange('second_dunning_after_days', parseInt(e.target.value) || 0)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="final_dunning_after_days">Letzte Mahnung nach (Tagen)</Label>
                  <Input
                    id="final_dunning_after_days"
                    type="number"
                    min={0}
                    value={formData.final_dunning_after_days}
                    onChange={(e) => handleChange('final_dunning_after_days', parseInt(e.target.value) || 0)}
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Gebühren */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Euro className="h-5 w-5" />
                Gebühren
              </CardTitle>
              <CardDescription>
                Legen Sie die Mahngebühren und Verzugszinsen fest
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="first_dunning_fee">1. Mahnung Gebühr (EUR)</Label>
                  <Input
                    id="first_dunning_fee"
                    type="number"
                    step="0.01"
                    min={0}
                    value={formData.first_dunning_fee}
                    onChange={(e) => handleChange('first_dunning_fee', parseFloat(e.target.value) || 0)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="second_dunning_fee">2. Mahnung Gebühr (EUR)</Label>
                  <Input
                    id="second_dunning_fee"
                    type="number"
                    step="0.01"
                    min={0}
                    value={formData.second_dunning_fee}
                    onChange={(e) => handleChange('second_dunning_fee', parseFloat(e.target.value) || 0)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="final_dunning_fee">Letzte Mahnung Gebühr (EUR)</Label>
                  <Input
                    id="final_dunning_fee"
                    type="number"
                    step="0.01"
                    min={0}
                    value={formData.final_dunning_fee}
                    onChange={(e) => handleChange('final_dunning_fee', parseFloat(e.target.value) || 0)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="late_interest_rate">Verzugszinsen (%)</Label>
                  <Input
                    id="late_interest_rate"
                    type="number"
                    step="0.01"
                    min={0}
                    value={formData.late_interest_rate}
                    onChange={(e) => handleChange('late_interest_rate', parseFloat(e.target.value) || 0)}
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="min_dunning_amount">Mindestbetrag (EUR)</Label>
                <Input
                  id="min_dunning_amount"
                  type="number"
                  step="0.01"
                  min={0}
                  value={formData.min_dunning_amount}
                  onChange={(e) => handleChange('min_dunning_amount', parseFloat(e.target.value) || 0)}
                />
                <p className="text-xs text-muted-foreground">
                  Rechnungen unter diesem Betrag werden nicht gemahnt
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Automatisierung */}
          <Card>
            <CardHeader>
              <CardTitle>Automatisierung</CardTitle>
              <CardDescription>
                Steuern Sie die automatische Verarbeitung
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label htmlFor="auto_process">Automatische Verarbeitung</Label>
                  <p className="text-xs text-muted-foreground">
                    Mahnungen werden automatisch erstellt und versendet
                  </p>
                </div>
                <Switch
                  id="auto_process"
                  checked={formData.auto_process_enabled}
                  onCheckedChange={(checked) => handleChange('auto_process_enabled', checked)}
                />
              </div>
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label htmlFor="dry_run">Testmodus (Dry Run)</Label>
                  <p className="text-xs text-muted-foreground">
                    Mahnungen werden erstellt aber nicht versendet
                  </p>
                </div>
                <Switch
                  id="dry_run"
                  checked={formData.dry_run_mode}
                  onCheckedChange={(checked) => handleChange('dry_run_mode', checked)}
                />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Statistics */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Aktuelle Statistiken</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {isLoadingStats ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : stats ? (
                <>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-muted-foreground">Aktive Mahnungen</span>
                      <Badge variant="default">{stats.active_dunnings_total}</Badge>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <span className="text-sm font-medium">Nach Stufe</span>
                    <div className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">Erinnerung</span>
                        <span>{stats.by_level['0'] || 0}</span>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">1. Mahnung</span>
                        <span>{stats.by_level['1'] || 0}</span>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">2. Mahnung</span>
                        <span>{stats.by_level['2'] || 0}</span>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">Letzte Mahnung</span>
                        <span>{stats.by_level['3'] || 0}</span>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-2 pt-4 border-t">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-muted-foreground">Gebühren eingenommen</span>
                      <span className="font-medium">
                        {stats.total_fees_collected.toLocaleString('de-DE', {
                          style: 'currency',
                          currency: 'EUR',
                        })}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-muted-foreground">Gebühren ausstehend</span>
                      <span className="font-medium">
                        {stats.total_outstanding_fees.toLocaleString('de-DE', {
                          style: 'currency',
                          currency: 'EUR',
                        })}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-muted-foreground">Durchschn. Bearbeitungszeit</span>
                      <span className="font-medium">{Math.round(stats.avg_resolution_days)} Tage</span>
                    </div>
                  </div>
                </>
              ) : (
                <div className="text-center py-8 text-muted-foreground text-sm">
                  Keine Statistiken verfügbar
                </div>
              )}
            </CardContent>
          </Card>

          {/* Info Card */}
          <Card>
            <CardHeader>
              <CardTitle>Hinweise</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div>
                <strong>Mahnstufen:</strong>
                <ul className="list-disc list-inside mt-1 text-muted-foreground">
                  <li>Stufe 0: Zahlungserinnerung</li>
                  <li>Stufe 1: Erste Mahnung</li>
                  <li>Stufe 2: Zweite Mahnung</li>
                  <li>Stufe 3: Letzte Mahnung</li>
                </ul>
              </div>
              <div>
                <strong>Verzugszinsen:</strong>
                <p className="text-muted-foreground mt-1">
                  Werden nach BGB §288 berechnet. Die angegebene Rate wird auf den ausstehenden Betrag angewendet.
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
