/**
 * RetentionSettings Component
 *
 * Verwaltung der Aufbewahrungsfristen nach GoBD.
 */

import { useState } from 'react'
import { Clock, RotateCcw, Save, Info } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import {
  useRetentionSettings,
  useUpdateRetentionSetting,
  useResetRetentionSetting,
} from '../hooks/use-gobd'
import type { RetentionSetting } from '../types'

const CATEGORY_LABELS: Record<string, string> = {
  invoice: 'Rechnungen',
  contract: 'Vertraege',
  correspondence: 'Korrespondenz',
  tax_document: 'Steuerdokumente',
  bank_statement: 'Kontoauszuege',
  receipt: 'Belege',
  other: 'Sonstige',
}

const DEFAULT_YEARS: Record<string, number> = {
  invoice: 10,
  contract: 10,
  correspondence: 6,
  tax_document: 10,
  bank_statement: 10,
  receipt: 10,
  other: 6,
}

interface EditDialogProps {
  setting: RetentionSetting
  onSave: (years: number, description: string, legalBasis: string) => void
  isPending: boolean
}

function EditDialog({ setting, onSave, isPending }: EditDialogProps) {
  const [years, setYears] = useState(setting.years)
  const [description, setDescription] = useState(setting.description)
  const [legalBasis, setLegalBasis] = useState(setting.legal_basis)
  const [open, setOpen] = useState(false)

  const handleSave = () => {
    onSave(years, description, legalBasis)
    setOpen(false)
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm">
          Bearbeiten
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Aufbewahrungsfrist bearbeiten</DialogTitle>
          <DialogDescription>
            Kategorie: {CATEGORY_LABELS[setting.category] || setting.category}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="years">Aufbewahrungsdauer (Jahre)</Label>
            <Input
              id="years"
              type="number"
              min={1}
              max={30}
              value={years}
              onChange={(e) => setYears(parseInt(e.target.value) || 1)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="description">Beschreibung</Label>
            <Textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Beschreibung der Aufbewahrungsfrist..."
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="legal-basis">Rechtsgrundlage</Label>
            <Textarea
              id="legal-basis"
              value={legalBasis}
              onChange={(e) => setLegalBasis(e.target.value)}
              placeholder="z.B. § 147 AO, § 257 HGB..."
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Abbrechen
          </Button>
          <Button onClick={handleSave} disabled={isPending}>
            <Save className="mr-2 h-4 w-4" />
            Speichern
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function RetentionSettings() {
  const { data: settings, isLoading } = useRetentionSettings()
  const updateSetting = useUpdateRetentionSetting()
  const resetSetting = useResetRetentionSetting()

  const handleUpdate = (category: string, years: number, description: string, legalBasis: string) => {
    updateSetting.mutate({
      category,
      update: { years, description, legal_basis: legalBasis },
    })
  }

  const handleReset = (category: string) => {
    if (confirm('Aufbewahrungsfrist auf Standardwert zuruecksetzen?')) {
      resetSetting.mutate(category)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Clock className="h-5 w-5" />
          Aufbewahrungsfristen
        </CardTitle>
        <CardDescription>
          Konfigurieren Sie die gesetzlichen Aufbewahrungsfristen nach GoBD. Aenderungen gelten nur
          fuer neu archivierte Dokumente.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Kategorie</TableHead>
                <TableHead>Dauer</TableHead>
                <TableHead>Rechtsgrundlage</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Aktionen</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center py-8 text-muted-foreground">
                    Laden...
                  </TableCell>
                </TableRow>
              ) : settings && settings.length > 0 ? (
                settings.map((setting) => (
                  <TableRow key={setting.id}>
                    <TableCell className="font-medium">
                      <div className="flex items-center gap-2">
                        {CATEGORY_LABELS[setting.category] || setting.category}
                        {setting.description && (
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger>
                                <Info className="h-4 w-4 text-muted-foreground" />
                              </TooltipTrigger>
                              <TooltipContent>
                                <p className="max-w-xs">{setting.description}</p>
                              </TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary">{setting.years} Jahre</Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground max-w-[200px] truncate">
                      {setting.legal_basis || '-'}
                    </TableCell>
                    <TableCell>
                      {setting.is_custom ? (
                        <Badge variant="outline" className="text-blue-600">
                          Angepasst
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-green-600">
                          Standard
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        <EditDialog
                          setting={setting}
                          onSave={(years, desc, basis) =>
                            handleUpdate(setting.category, years, desc, basis)
                          }
                          isPending={updateSetting.isPending}
                        />
                        {setting.is_custom && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleReset(setting.category)}
                            disabled={resetSetting.isPending}
                          >
                            <RotateCcw className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={5} className="text-center py-8 text-muted-foreground">
                    Keine Einstellungen gefunden
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>

        {/* Info Box */}
        <div className="mt-6 rounded-md border border-blue-500/30 bg-blue-500/10 p-4">
          <h4 className="font-medium text-blue-700 mb-2">Gesetzliche Grundlagen</h4>
          <ul className="text-sm text-blue-600 space-y-1">
            <li>
              <strong>§ 147 AO</strong>: Aufbewahrung von Buchungsbelegen (10 Jahre)
            </li>
            <li>
              <strong>§ 257 HGB</strong>: Aufbewahrung von Handelsbriefwechsel (6 Jahre)
            </li>
            <li>
              <strong>§ 14b UStG</strong>: Aufbewahrung von Rechnungen (10 Jahre)
            </li>
          </ul>
        </div>
      </CardContent>
    </Card>
  )
}
