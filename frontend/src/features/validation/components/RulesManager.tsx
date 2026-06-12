/**
 * RulesManager
 *
 * Verwaltung von Validierungsregeln für automatische Stichprobenauswahl.
 * Ermöglicht CRUD-Operationen auf ValidationRules.
 */

import { useState } from 'react';
import {
  Plus,
  Pencil,
  Trash2,
  ToggleLeft,
  ToggleRight,
  AlertCircle,
  Settings2,
  RefreshCw,
  Search,
  MoreHorizontal,
  Clock,
  FileText,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { toast } from 'sonner';
import {
  useValidationRules,
  useCreateRule,
  useUpdateRule,
  useDeleteRule,
} from '../hooks/use-validation-queue';
import { RULE_TYPE_LABELS } from '../types/validation-queue.types';
import type { ValidationRule, ValidationRuleCreate, ValidationRuleUpdate } from '../types/validation-queue.types';
import { RuleFormDialog } from './RuleFormDialog';
import { SampleConfigDialog } from './SampleConfigDialog';

export function RulesManager() {
  const [searchQuery, setSearchQuery] = useState('');
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<ValidationRule | null>(null);
  const [configDialogOpen, setConfigDialogOpen] = useState(false);

  // Queries & Mutations
  const { data: rulesData, isLoading, error, refetch } = useValidationRules();
  const createRule = useCreateRule();
  const updateRule = useUpdateRule();
  const deleteRule = useDeleteRule();

  // Filter rules by search
  const filteredRules = rulesData?.rules.filter((rule) =>
    rule.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    rule.description?.toLowerCase().includes(searchQuery.toLowerCase())
  ) || [];

  // Handlers
  const handleCreateRule = async (data: ValidationRuleCreate) => {
    try {
      await createRule.mutateAsync(data);
      toast.success('Regel erstellt');
      setCreateDialogOpen(false);
    } catch {
      toast.error('Fehler beim Erstellen der Regel');
    }
  };

  const handleUpdateRule = async (data: ValidationRuleUpdate) => {
    if (!editingRule) return;
    try {
      await updateRule.mutateAsync({ ruleId: editingRule.id, data });
      toast.success('Regel aktualisiert');
      setEditDialogOpen(false);
      setEditingRule(null);
    } catch {
      toast.error('Fehler beim Aktualisieren der Regel');
    }
  };

  const handleToggleRule = async (rule: ValidationRule) => {
    try {
      await updateRule.mutateAsync({
        ruleId: rule.id,
        data: { is_active: !rule.is_active },
      });
      toast.success(rule.is_active ? 'Regel deaktiviert' : 'Regel aktiviert');
    } catch {
      toast.error('Fehler beim Umschalten der Regel');
    }
  };

  const handleDeleteRule = async (ruleId: string) => {
    if (!window.confirm('Diese Regel wirklich löschen?')) return;
    try {
      await deleteRule.mutateAsync(ruleId);
      toast.success('Regel gelöscht');
    } catch {
      toast.error('Fehler beim Löschen der Regel');
    }
  };

  const handleEditClick = (rule: ValidationRule) => {
    setEditingRule(rule);
    setEditDialogOpen(true);
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Validierungsregeln</h2>
          <p className="text-sm text-muted-foreground">
            Regeln für automatische Stichprobenauswahl verwalten
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={() => setConfigDialogOpen(true)}
          >
            <Settings2 className="w-4 h-4 mr-2" />
            Stichproben-Config
          </Button>
          <Button onClick={() => setCreateDialogOpen(true)}>
            <Plus className="w-4 h-4 mr-2" />
            Neue Regel
          </Button>
        </div>
      </div>

      {/* Search */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Regeln suchen..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>
        <Button
          variant="outline"
          size="icon"
          onClick={() => refetch()}
          disabled={isLoading}
        >
          <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      {/* Error State */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 text-destructive">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-5 h-5" />
            <p className="font-medium">Fehler beim Laden der Regeln</p>
          </div>
          <p className="text-sm mt-1">{(error as Error).message}</p>
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && filteredRules.length === 0 && (
        <div className="text-center py-12 bg-muted/30 rounded-lg">
          <Settings2 className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
          <h3 className="text-lg font-medium mb-2">Keine Regeln gefunden</h3>
          <p className="text-muted-foreground mb-4">
            {searchQuery
              ? 'Keine Regeln entsprechen der Suche'
              : 'Erstellen Sie Ihre erste Validierungsregel'}
          </p>
          {!searchQuery && (
            <Button onClick={() => setCreateDialogOpen(true)}>
              <Plus className="w-4 h-4 mr-2" />
              Regel erstellen
            </Button>
          )}
        </div>
      )}

      {/* Rules Table */}
      {!isLoading && !error && filteredRules.length > 0 && (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Typ</TableHead>
                <TableHead>Priorität</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Getriggert</TableHead>
                <TableHead className="w-[80px]">Aktionen</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredRules.map((rule) => (
                <TableRow key={rule.id}>
                  <TableCell>
                    <div>
                      <div className="font-medium flex items-center gap-2">
                        {rule.name}
                        {rule.is_system && (
                          <Badge variant="outline" className="text-xs">
                            System
                          </Badge>
                        )}
                      </div>
                      {rule.description && (
                        <div className="text-sm text-muted-foreground truncate max-w-[300px]">
                          {rule.description}
                        </div>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary">
                      {RULE_TYPE_LABELS[rule.rule_type]}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <span className="font-medium">{rule.priority}</span>
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleToggleRule(rule)}
                      disabled={rule.is_system || updateRule.isPending}
                      className={rule.is_active ? 'text-green-600' : 'text-muted-foreground'}
                    >
                      {rule.is_active ? (
                        <>
                          <ToggleRight className="w-5 h-5 mr-1" />
                          Aktiv
                        </>
                      ) : (
                        <>
                          <ToggleLeft className="w-5 h-5 mr-1" />
                          Inaktiv
                        </>
                      )}
                    </Button>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <FileText className="w-4 h-4" />
                      <span>{rule.documents_matched}</span>
                      {rule.last_triggered_at && (
                        <>
                          <Clock className="w-4 h-4 ml-2" />
                          <span>
                            {new Date(rule.last_triggered_at).toLocaleDateString('de-DE')}
                          </span>
                        </>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon">
                          <MoreHorizontal className="w-4 h-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem
                          onClick={() => handleEditClick(rule)}
                          disabled={rule.is_system}
                        >
                          <Pencil className="w-4 h-4 mr-2" />
                          Bearbeiten
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          onClick={() => handleDeleteRule(rule.id)}
                          disabled={rule.is_system}
                          className="text-destructive"
                        >
                          <Trash2 className="w-4 h-4 mr-2" />
                          Löschen
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Dialoge */}
      <RuleFormDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
        onSubmit={(data) => handleCreateRule(data as ValidationRuleCreate)}
        isLoading={createRule.isPending}
      />

      <RuleFormDialog
        open={editDialogOpen}
        onOpenChange={(open) => {
          setEditDialogOpen(open);
          if (!open) setEditingRule(null);
        }}
        onSubmit={handleUpdateRule}
        isLoading={updateRule.isPending}
        initialData={editingRule || undefined}
      />

      <SampleConfigDialog
        open={configDialogOpen}
        onOpenChange={setConfigDialogOpen}
      />
    </div>
  );
}

export default RulesManager;
