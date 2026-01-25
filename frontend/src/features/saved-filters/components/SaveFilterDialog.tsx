/**
 * SaveFilterDialog - Dialog zum Erstellen/Bearbeiten von Filtern
 *
 * Phase 4.5: Frontend UX Enhancement
 */
import { useState, useEffect } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Switch } from "@/components/ui/switch"
import { Loader2, Save, Share2 } from "lucide-react"
import type { SavedFilter } from "../api/saved-filters-api"

export interface SaveFilterDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Aktueller Filter zum Bearbeiten (null = Neuanlage) */
  filter?: SavedFilter | null
  /** Aktuelle Filter-Konfiguration (bei Neuanlage) */
  currentFilterConfig?: Record<string, unknown>
  /** Callback beim Speichern */
  onSave: (data: {
    name: string
    description?: string
    filter_config: Record<string, unknown>
    is_shared: boolean
    is_default: boolean
  }) => Promise<void>
  /** Wird gerade gespeichert */
  isSaving?: boolean
}

export function SaveFilterDialog({
  open,
  onOpenChange,
  filter,
  currentFilterConfig,
  onSave,
  isSaving = false,
}: SaveFilterDialogProps) {
  const isEditing = !!filter
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [isShared, setIsShared] = useState(false)
  const [isDefault, setIsDefault] = useState(false)

  // Formular bei Oeffnen/Aendern zuruecksetzen
  useEffect(() => {
    if (open) {
      if (filter) {
        setName(filter.name)
        setDescription(filter.description || "")
        setIsShared(filter.is_shared)
        setIsDefault(filter.is_default)
      } else {
        setName("")
        setDescription("")
        setIsShared(false)
        setIsDefault(false)
      }
    }
  }, [open, filter])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return

    await onSave({
      name: name.trim(),
      description: description.trim() || undefined,
      filter_config: filter?.filter_config || currentFilterConfig || {},
      is_shared: isShared,
      is_default: isDefault,
    })
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>
              {isEditing ? "Filter bearbeiten" : "Filter speichern"}
            </DialogTitle>
            <DialogDescription>
              {isEditing
                ? "Aendern Sie die Einstellungen dieses Filters."
                : "Speichern Sie die aktuelle Filtereinstellung fuer spaetere Verwendung."}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="filter-name">Name *</Label>
              <Input
                id="filter-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="z.B. Offene Rechnungen"
                maxLength={255}
                required
                autoFocus
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="filter-description">Beschreibung</Label>
              <Textarea
                id="filter-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optionale Beschreibung fuer diesen Filter..."
                maxLength={1000}
                rows={2}
              />
            </div>

            <div className="flex items-center justify-between rounded-lg border p-3">
              <div className="space-y-0.5">
                <div className="flex items-center gap-2">
                  <Share2 className="h-4 w-4 text-muted-foreground" />
                  <Label htmlFor="filter-shared" className="font-medium">
                    Mit Team teilen
                  </Label>
                </div>
                <p className="text-xs text-muted-foreground">
                  Andere Teammitglieder koennen diesen Filter sehen
                </p>
              </div>
              <Switch
                id="filter-shared"
                checked={isShared}
                onCheckedChange={setIsShared}
              />
            </div>

            <div className="flex items-center justify-between rounded-lg border p-3">
              <div className="space-y-0.5">
                <Label htmlFor="filter-default" className="font-medium">
                  Als Standard verwenden
                </Label>
                <p className="text-xs text-muted-foreground">
                  Automatisch anwenden beim Oeffnen
                </p>
              </div>
              <Switch
                id="filter-default"
                checked={isDefault}
                onCheckedChange={setIsDefault}
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isSaving}
            >
              Abbrechen
            </Button>
            <Button type="submit" disabled={!name.trim() || isSaving}>
              {isSaving ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Speichern...
                </>
              ) : (
                <>
                  <Save className="mr-2 h-4 w-4" />
                  {isEditing ? "Aktualisieren" : "Speichern"}
                </>
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
