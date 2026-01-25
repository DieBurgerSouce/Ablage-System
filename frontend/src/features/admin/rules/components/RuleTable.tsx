/**
 * RuleTable Component
 *
 * Tabelle zur Anzeige von Business Rules.
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
import { MoreHorizontal, Pencil, Trash2, Play, Copy, History } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { de } from 'date-fns/locale'
import { toast } from '@/components/ui/use-toast'
import type { BusinessRule, RuleCategory } from '../types'
import { useUpdateRule, useDeleteRule } from '../api'

const CATEGORY_LABELS: Record<RuleCategory, string> = {
  approval: 'Genehmigung',
  compliance: 'Compliance',
  fraud: 'Fraud',
  workflow: 'Workflow',
  notification: 'Benachrichtigung',
  data_quality: 'Datenqualitaet',
  custom: 'Benutzerdefiniert',
}

const CATEGORY_COLORS: Record<RuleCategory, string> = {
  approval: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
  compliance: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300',
  fraud: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
  workflow: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
  notification: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300',
  data_quality: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-300',
  custom: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-300',
}

interface RuleTableProps {
  rules: BusinessRule[]
  isLoading: boolean
  onEdit: (rule: BusinessRule) => void
  onViewLogs?: (rule: BusinessRule) => void
  onDuplicate?: (rule: BusinessRule) => void
}

export function RuleTable({
  rules,
  isLoading,
  onEdit,
  onViewLogs,
  onDuplicate,
}: RuleTableProps) {
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [ruleToDelete, setRuleToDelete] = useState<BusinessRule | null>(null)

  const updateMutation = useUpdateRule()
  const deleteMutation = useDeleteRule()

  const handleToggleActive = async (rule: BusinessRule) => {
    try {
      await updateMutation.mutateAsync({
        id: rule.id,
        data: { is_active: !rule.is_active },
      })
      toast({
        title: rule.is_active ? 'Regel deaktiviert' : 'Regel aktiviert',
      })
    } catch {
      toast({
        title: 'Fehler',
        description: 'Status konnte nicht geaendert werden.',
        variant: 'destructive',
      })
    }
  }

  const handleDelete = async () => {
    if (!ruleToDelete) return

    try {
      await deleteMutation.mutateAsync(ruleToDelete.id)
      toast({
        title: 'Regel geloescht',
        description: `"${ruleToDelete.name}" wurde geloescht.`,
      })
    } catch {
      toast({
        title: 'Fehler',
        description: 'Regel konnte nicht geloescht werden.',
        variant: 'destructive',
      })
    } finally {
      setDeleteDialogOpen(false)
      setRuleToDelete(null)
    }
  }

  const confirmDelete = (rule: BusinessRule) => {
    setRuleToDelete(rule)
    setDeleteDialogOpen(true)
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    )
  }

  if (rules.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <p>Keine Regeln gefunden.</p>
        <p className="text-sm mt-1">
          Erstellen Sie Ihre erste Regel, um die automatische Verarbeitung zu starten.
        </p>
      </div>
    )
  }

  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Aktiv</TableHead>
            <TableHead>Name</TableHead>
            <TableHead>Kategorie</TableHead>
            <TableHead className="text-center">Prioritaet</TableHead>
            <TableHead className="text-right">Ausfuehrungen</TableHead>
            <TableHead className="text-right">Matches</TableHead>
            <TableHead>Zuletzt</TableHead>
            <TableHead className="w-[50px]"></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rules.map((rule) => (
            <TableRow key={rule.id}>
              <TableCell>
                <Switch
                  checked={rule.is_active}
                  onCheckedChange={() => handleToggleActive(rule)}
                  disabled={updateMutation.isPending}
                />
              </TableCell>
              <TableCell>
                <div>
                  <div className="font-medium">{rule.name}</div>
                  {rule.code && (
                    <div className="text-xs text-muted-foreground font-mono">
                      {rule.code}
                    </div>
                  )}
                  {rule.description && (
                    <div className="text-sm text-muted-foreground truncate max-w-[300px]">
                      {rule.description}
                    </div>
                  )}
                </div>
              </TableCell>
              <TableCell>
                <Badge
                  variant="secondary"
                  className={CATEGORY_COLORS[rule.category]}
                >
                  {CATEGORY_LABELS[rule.category]}
                </Badge>
              </TableCell>
              <TableCell className="text-center">
                <Badge variant="outline">{rule.priority}</Badge>
              </TableCell>
              <TableCell className="text-right font-mono">
                {rule.execution_count.toLocaleString('de-DE')}
              </TableCell>
              <TableCell className="text-right font-mono">
                {rule.match_count.toLocaleString('de-DE')}
                {rule.execution_count > 0 && (
                  <span className="text-muted-foreground text-xs ml-1">
                    ({Math.round((rule.match_count / rule.execution_count) * 100)}%)
                  </span>
                )}
              </TableCell>
              <TableCell className="text-muted-foreground text-sm">
                {rule.last_executed_at
                  ? formatDistanceToNow(new Date(rule.last_executed_at), {
                      addSuffix: true,
                      locale: de,
                    })
                  : '-'}
              </TableCell>
              <TableCell>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon">
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => onEdit(rule)}>
                      <Pencil className="h-4 w-4 mr-2" />
                      Bearbeiten
                    </DropdownMenuItem>
                    {onDuplicate && (
                      <DropdownMenuItem onClick={() => onDuplicate(rule)}>
                        <Copy className="h-4 w-4 mr-2" />
                        Duplizieren
                      </DropdownMenuItem>
                    )}
                    {onViewLogs && (
                      <DropdownMenuItem onClick={() => onViewLogs(rule)}>
                        <History className="h-4 w-4 mr-2" />
                        Ausfuehrungslog
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onClick={() => confirmDelete(rule)}
                      className="text-destructive focus:text-destructive"
                    >
                      <Trash2 className="h-4 w-4 mr-2" />
                      Loeschen
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Regel loeschen?</AlertDialogTitle>
            <AlertDialogDescription>
              Moechten Sie die Regel "{ruleToDelete?.name}" wirklich loeschen?
              Diese Aktion kann nicht rueckgaengig gemacht werden.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Loeschen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
