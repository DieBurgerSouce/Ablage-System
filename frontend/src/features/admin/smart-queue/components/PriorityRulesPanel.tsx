/**
 * Priority Rules Panel
 *
 * Verwaltung der automatischen Priorisierungs-Regeln.
 */

import { useState } from 'react';
import {
  Settings,
  Plus,
  Pencil,
  Trash2,
  ToggleLeft,
  ToggleRight,
  Loader2,
  RefreshCw,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { toast } from 'sonner';
import {
  usePriorityRules,
  useSavePriorityRule,
  useDeletePriorityRule,
  useRecalculatePriorities,
  type PriorityRule,
} from '../hooks/useSmartQueue';

const CONDITION_TYPES = [
  { value: 'skonto_days', label: 'Skonto-Frist (Tage)', description: 'Prioritaet erhoehen wenn Skonto-Frist <= X Tage' },
  { value: 'amount_threshold', label: 'Betrag-Schwelle', description: 'Prioritaet erhoehen wenn Betrag >= X EUR' },
  { value: 'document_type', label: 'Dokumenttyp', description: 'Prioritaet basierend auf Dokumenttyp' },
  { value: 'entity_type', label: 'Entity-Typ', description: 'Prioritaet basierend auf Kunden-/Lieferantentyp' },
  { value: 'custom', label: 'Benutzerdefiniert', description: 'Eigene Regel-Expression' },
];

interface RuleFormData {
  name: string;
  description: string;
  condition_type: string;
  condition_value: string;
  priority_boost: number;
  enabled: boolean;
}

const DEFAULT_FORM: RuleFormData = {
  name: '',
  description: '',
  condition_type: 'skonto_days',
  condition_value: '5',
  priority_boost: 3,
  enabled: true,
};

function RuleFormDialog({
  open,
  onOpenChange,
  rule,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  rule?: PriorityRule;
}) {
  const [formData, setFormData] = useState<RuleFormData>(
    rule
      ? {
          name: rule.name,
          description: rule.description,
          condition_type: rule.condition_type,
          condition_value: rule.condition_value,
          priority_boost: rule.priority_boost,
          enabled: rule.enabled,
        }
      : DEFAULT_FORM
  );

  const saveMutation = useSavePriorityRule();

  const handleSubmit = async () => {
    if (!formData.name.trim()) {
      toast.error('Bitte Namen eingeben');
      return;
    }

    try {
      await saveMutation.mutateAsync({
        id: rule?.id,
        ...formData,
        condition_type: formData.condition_type as PriorityRule['condition_type'],
      });
      toast.success(rule ? 'Regel aktualisiert' : 'Regel erstellt');
      onOpenChange(false);
    } catch {
      toast.error('Fehler beim Speichern');
    }
  };

  const conditionType = CONDITION_TYPES.find((c) => c.value === formData.condition_type);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{rule ? 'Regel bearbeiten' : 'Neue Regel erstellen'}</DialogTitle>
          <DialogDescription>
            Definieren Sie eine automatische Priorisierungs-Regel.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="name">Name</Label>
            <Input
              id="name"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder="z.B. Skonto-Frist kritisch"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="description">Beschreibung</Label>
            <Input
              id="description"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="Optionale Beschreibung"
            />
          </div>

          <div className="space-y-2">
            <Label>Bedingungstyp</Label>
            <Select
              value={formData.condition_type}
              onValueChange={(v) => setFormData({ ...formData, condition_type: v })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CONDITION_TYPES.map((type) => (
                  <SelectItem key={type.value} value={type.value}>
                    {type.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {conditionType && (
              <p className="text-xs text-muted-foreground">{conditionType.description}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="condition_value">Wert</Label>
            <Input
              id="condition_value"
              value={formData.condition_value}
              onChange={(e) => setFormData({ ...formData, condition_value: e.target.value })}
              placeholder={
                formData.condition_type === 'skonto_days'
                  ? 'z.B. 5 (Tage)'
                  : formData.condition_type === 'amount_threshold'
                    ? 'z.B. 10000 (EUR)'
                    : 'Wert eingeben'
              }
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="priority_boost">Prioritaets-Erhoehung</Label>
            <Input
              id="priority_boost"
              type="number"
              min={1}
              max={5}
              value={formData.priority_boost}
              onChange={(e) =>
                setFormData({ ...formData, priority_boost: parseInt(e.target.value) || 1 })
              }
            />
            <p className="text-xs text-muted-foreground">
              Erhoehung der Basis-Prioritaet (1-5)
            </p>
          </div>

          <div className="flex items-center justify-between">
            <Label htmlFor="enabled">Regel aktiv</Label>
            <Switch
              id="enabled"
              checked={formData.enabled}
              onCheckedChange={(checked) => setFormData({ ...formData, enabled: checked })}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Abbrechen
          </Button>
          <Button onClick={handleSubmit} disabled={saveMutation.isPending}>
            {saveMutation.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            {rule ? 'Speichern' : 'Erstellen'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function PriorityRulesPanel() {
  const { data: rules, isLoading } = usePriorityRules();
  const deleteMutation = useDeletePriorityRule();
  const recalculateMutation = useRecalculatePriorities();
  const saveMutation = useSavePriorityRule();

  const [editingRule, setEditingRule] = useState<PriorityRule | undefined>();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [deleteRule, setDeleteRule] = useState<PriorityRule | null>(null);

  const handleToggle = async (rule: PriorityRule) => {
    try {
      await saveMutation.mutateAsync({
        ...rule,
        enabled: !rule.enabled,
      });
      toast.success(rule.enabled ? 'Regel deaktiviert' : 'Regel aktiviert');
    } catch {
      toast.error('Fehler beim Aendern');
    }
  };

  const handleDelete = async () => {
    if (!deleteRule) return;
    try {
      await deleteMutation.mutateAsync(deleteRule.id);
      toast.success('Regel geloescht');
      setDeleteRule(null);
    } catch {
      toast.error('Fehler beim Loeschen');
    }
  };

  const handleRecalculate = async () => {
    try {
      const result = await recalculateMutation.mutateAsync();
      toast.success(`${result.recalculated} Prioritaeten neu berechnet`);
    } catch {
      toast.error('Fehler bei der Neuberechnung');
    }
  };

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Settings className="h-5 w-5" />
              Priorisierungs-Regeln
            </CardTitle>
            <CardDescription>
              Automatische Prioritaets-Zuweisung basierend auf Dokumenteigenschaften
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleRecalculate}
              disabled={recalculateMutation.isPending}
            >
              {recalculateMutation.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4 mr-2" />
              )}
              Neu berechnen
            </Button>
            <Button
              size="sm"
              onClick={() => {
                setEditingRule(undefined);
                setIsFormOpen(true);
              }}
            >
              <Plus className="h-4 w-4 mr-2" />
              Neue Regel
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : rules && rules.length > 0 ? (
            <div className="space-y-3">
              {rules.map((rule) => (
                <div
                  key={rule.id}
                  className={`flex items-center justify-between p-4 border rounded-lg ${
                    rule.enabled ? '' : 'opacity-50'
                  }`}
                >
                  <div className="flex items-center gap-4">
                    <button
                      onClick={() => handleToggle(rule)}
                      className="text-muted-foreground hover:text-foreground"
                    >
                      {rule.enabled ? (
                        <ToggleRight className="h-6 w-6 text-green-500" />
                      ) : (
                        <ToggleLeft className="h-6 w-6" />
                      )}
                    </button>
                    <div>
                      <p className="font-medium">{rule.name}</p>
                      <p className="text-sm text-muted-foreground">{rule.description}</p>
                      <div className="flex items-center gap-2 mt-1">
                        <Badge variant="outline" className="text-xs">
                          {CONDITION_TYPES.find((c) => c.value === rule.condition_type)?.label}
                        </Badge>
                        <Badge variant="secondary" className="text-xs">
                          +{rule.priority_boost} Prioritaet
                        </Badge>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setEditingRule(rule);
                        setIsFormOpen(true);
                      }}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-red-500 hover:text-red-600"
                      onClick={() => setDeleteRule(rule)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <Settings className="h-12 w-12 mx-auto mb-4 opacity-20" />
              <p>Keine Regeln konfiguriert</p>
              <Button
                variant="outline"
                size="sm"
                className="mt-4"
                onClick={() => {
                  setEditingRule(undefined);
                  setIsFormOpen(true);
                }}
              >
                <Plus className="h-4 w-4 mr-2" />
                Erste Regel erstellen
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <RuleFormDialog
        open={isFormOpen}
        onOpenChange={setIsFormOpen}
        rule={editingRule}
      />

      <AlertDialog open={!!deleteRule} onOpenChange={() => setDeleteRule(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Regel loeschen?</AlertDialogTitle>
            <AlertDialogDescription>
              Die Regel "{deleteRule?.name}" wird unwiderruflich geloescht.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-red-500 hover:bg-red-600"
            >
              Loeschen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
