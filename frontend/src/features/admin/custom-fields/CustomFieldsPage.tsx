/**
 * CustomFieldsPage
 *
 * Admin-Seite fuer die Verwaltung benutzerdefinierter Felddefinitionen.
 */

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import {
  Settings2,
  Plus,
  Search,
  Hash,
  CheckCircle,
  Filter,
} from 'lucide-react'
import { FieldDefinitionTable, FieldDefinitionDialog } from './components'
import { useCustomFieldDefinitions } from './api'
import { DOCUMENT_TYPE_OPTIONS } from './types'
import type { CustomFieldDefinitionResponse } from './types'

export function CustomFieldsPage() {
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingDefinition, setEditingDefinition] =
    useState<CustomFieldDefinitionResponse | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [docTypeFilter, setDocTypeFilter] = useState<string>('all')
  const [showInactive, setShowInactive] = useState(false)

  const { data, isLoading } = useCustomFieldDefinitions({
    document_type: docTypeFilter === 'all' ? undefined : docTypeFilter,
    include_inactive: showInactive,
  })

  const handleEdit = (definition: CustomFieldDefinitionResponse) => {
    setEditingDefinition(definition)
    setDialogOpen(true)
  }

  const handleCreate = () => {
    setEditingDefinition(null)
    setDialogOpen(true)
  }

  const handleDialogClose = (open: boolean) => {
    setDialogOpen(open)
    if (!open) {
      setEditingDefinition(null)
    }
  }

  // Lokale Filterung nach Suchbegriff
  const allDefinitions = data?.items ?? []
  const filteredDefinitions = searchQuery
    ? allDefinitions.filter(
        (d) =>
          d.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          d.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
          (d.description ?? '')
            .toLowerCase()
            .includes(searchQuery.toLowerCase())
      )
    : allDefinitions

  // Stats
  const totalCount = allDefinitions.length
  const activeCount = allDefinitions.filter((d) => d.is_active).length
  const requiredCount = allDefinitions.filter((d) => d.required).length

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Settings2 className="h-6 w-6" />
            Benutzerdefinierte Felder
          </h1>
          <p className="text-muted-foreground">
            Verwalten Sie eigene Felder fuer Ihre Dokumente.
          </p>
        </div>

        <Button onClick={handleCreate}>
          <Plus className="h-4 w-4 mr-2" />
          Neues Feld
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Felder gesamt
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <Hash className="h-4 w-4 text-muted-foreground" />
              <span className="text-2xl font-bold">{totalCount}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Aktive Felder
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <CheckCircle className="h-4 w-4 text-green-500" />
              <span className="text-2xl font-bold">{activeCount}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Pflichtfelder
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <Filter className="h-4 w-4 text-red-500" />
              <span className="text-2xl font-bold">{requiredCount}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Tabelle */}
      <Card>
        <CardHeader>
          <div className="flex flex-col md:flex-row md:items-center gap-4">
            <div className="flex-1">
              <CardTitle>Felddefinitionen</CardTitle>
              <CardDescription>
                Alle benutzerdefinierten Felder Ihres Mandanten.
              </CardDescription>
            </div>

            <div className="flex gap-2 items-center">
              <div className="relative">
                <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Suchen..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-8 w-[180px]"
                />
              </div>

              <Select value={docTypeFilter} onValueChange={setDocTypeFilter}>
                <SelectTrigger className="w-[160px]">
                  <SelectValue placeholder="Dokumenttyp" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Alle Typen</SelectItem>
                  {DOCUMENT_TYPE_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <div className="flex items-center gap-2">
                <Switch
                  checked={showInactive}
                  onCheckedChange={setShowInactive}
                  id="show-inactive"
                />
                <Label htmlFor="show-inactive" className="text-sm whitespace-nowrap">
                  Inaktive
                </Label>
              </div>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <FieldDefinitionTable
            definitions={filteredDefinitions}
            isLoading={isLoading}
            onEdit={handleEdit}
          />
        </CardContent>
      </Card>

      {/* Dialog */}
      <FieldDefinitionDialog
        open={dialogOpen}
        onOpenChange={handleDialogClose}
        definition={editingDefinition}
      />
    </div>
  )
}
