/**
 * FieldDefinitionTable
 *
 * Tabelle zur Anzeige aller benutzerdefinierten Felddefinitionen.
 */

import { useState } from 'react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { Skeleton } from '@/components/ui/skeleton'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { MoreHorizontal, Pencil, Trash2, GripVertical } from 'lucide-react'
import { toast } from '@/components/ui/use-toast'
import type { CustomFieldDefinitionResponse, FieldType } from '../types'
import { FIELD_TYPE_LABELS } from '../types'
import { useDeleteFieldDefinition, useUpdateFieldDefinition } from '../api'

const FIELD_TYPE_COLORS: Record<FieldType, string> = {
  text: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  number: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  date: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400',
  boolean: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  dropdown: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-400',
  multi_select: 'bg-pink-100 text-pink-800 dark:bg-pink-900/30 dark:text-pink-400',
  lookup: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
}

interface FieldDefinitionTableProps {
  definitions: CustomFieldDefinitionResponse[]
  isLoading: boolean
  onEdit: (definition: CustomFieldDefinitionResponse) => void
}

export function FieldDefinitionTable({
  definitions,
  isLoading,
  onEdit,
}: FieldDefinitionTableProps) {
  const [deleteId, setDeleteId] = useState<string | null>(null)
  const deleteMutation = useDeleteFieldDefinition()
  const updateMutation = useUpdateFieldDefinition()

  const handleDelete = async () => {
    if (!deleteId) return
    try {
      await deleteMutation.mutateAsync(deleteId)
      toast({
        title: 'Feld deaktiviert',
        description: 'Die Felddefinition wurde deaktiviert.',
      })
    } catch {
      toast({
        title: 'Fehler',
        description: 'Die Felddefinition konnte nicht deaktiviert werden.',
        variant: 'destructive',
      })
    }
    setDeleteId(null)
  }

  const handleToggleActive = async (
    definition: CustomFieldDefinitionResponse,
    isActive: boolean
  ) => {
    try {
      await updateMutation.mutateAsync({
        id: definition.id,
        data: { is_active: isActive },
      })
      toast({
        title: isActive ? 'Feld aktiviert' : 'Feld deaktiviert',
        description: `"${definition.label}" wurde ${isActive ? 'aktiviert' : 'deaktiviert'}.`,
      })
    } catch {
      toast({
        title: 'Fehler',
        description: 'Status konnte nicht geaendert werden.',
        variant: 'destructive',
      })
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    )
  }

  if (definitions.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <GripVertical className="h-12 w-12 mx-auto mb-4 opacity-30" />
        <p className="text-lg font-medium">Keine Felddefinitionen vorhanden</p>
        <p className="text-sm mt-1">
          Erstellen Sie Ihr erstes benutzerdefiniertes Feld.
        </p>
      </div>
    )
  }

  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[200px]">Name</TableHead>
            <TableHead>Label</TableHead>
            <TableHead>Typ</TableHead>
            <TableHead>Dokumenttyp</TableHead>
            <TableHead className="text-center">Pflicht</TableHead>
            <TableHead className="text-center">Aktiv</TableHead>
            <TableHead className="text-right">Aktionen</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {definitions.map((definition) => (
            <TableRow key={definition.id}>
              <TableCell className="font-mono text-sm">
                {definition.name}
              </TableCell>
              <TableCell>
                <div>
                  <div className="font-medium">{definition.label}</div>
                  {definition.description && (
                    <div className="text-xs text-muted-foreground truncate max-w-[200px]">
                      {definition.description}
                    </div>
                  )}
                </div>
              </TableCell>
              <TableCell>
                <Badge
                  variant="secondary"
                  className={FIELD_TYPE_COLORS[definition.field_type]}
                >
                  {FIELD_TYPE_LABELS[definition.field_type]}
                </Badge>
              </TableCell>
              <TableCell>
                {definition.document_type ? (
                  <Badge variant="outline">{definition.document_type}</Badge>
                ) : (
                  <span className="text-muted-foreground text-sm">Alle</span>
                )}
              </TableCell>
              <TableCell className="text-center">
                {definition.required ? (
                  <Badge variant="default" className="bg-red-600">
                    Ja
                  </Badge>
                ) : (
                  <span className="text-muted-foreground text-sm">Nein</span>
                )}
              </TableCell>
              <TableCell className="text-center">
                <Switch
                  checked={definition.is_active}
                  onCheckedChange={(checked) =>
                    handleToggleActive(definition, checked)
                  }
                />
              </TableCell>
              <TableCell className="text-right">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" className="h-8 w-8 p-0">
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => onEdit(definition)}>
                      <Pencil className="h-4 w-4 mr-2" />
                      Bearbeiten
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onClick={() => setDeleteId(definition.id)}
                      className="text-destructive"
                    >
                      <Trash2 className="h-4 w-4 mr-2" />
                      Deaktivieren
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      {/* Loeschen-Bestaetigung */}
      <AlertDialog
        open={!!deleteId}
        onOpenChange={(open) => !open && setDeleteId(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Felddefinition deaktivieren?</AlertDialogTitle>
            <AlertDialogDescription>
              Das Feld wird deaktiviert und nicht mehr in neuen Dokumenten
              angezeigt. Bestehende Werte bleiben erhalten.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete}>
              Deaktivieren
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
