/**
 * SubstitutionManager Component
 * Manage user substitution/absence rules
 */

import { useState } from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Plus, Trash2, Calendar, User } from 'lucide-react';
import {
  useSubstitutionRules,
  useCreateSubstitutionRule,
  useDeleteSubstitutionRule,
} from '../hooks/use-approval-enhanced-queries';
import { UI_LABELS } from '../types/approval-enhanced-types';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';

const SCOPE_OPTIONS = [
  { value: 'all', label: 'Alle Genehmigungen' },
  { value: 'invoices', label: 'Nur Rechnungen' },
  { value: 'contracts', label: 'Nur Verträge' },
  { value: 'expenses', label: 'Nur Ausgaben' },
];

export function SubstitutionManager() {
  const { data: rules, isLoading } = useSubstitutionRules();
  const createMutation = useCreateSubstitutionRule();
  const deleteMutation = useDeleteSubstitutionRule();

  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [formData, setFormData] = useState({
    original_user_id: 1,
    substitute_user_id: 2,
    start_date: '',
    end_date: '',
    scope: 'all',
  });

  const handleCreate = () => {
    createMutation.mutate(formData, {
      onSuccess: () => {
        setIsCreateDialogOpen(false);
        setFormData({
          original_user_id: 1,
          substitute_user_id: 2,
          start_date: '',
          end_date: '',
          scope: 'all',
        });
      },
    });
  };

  const handleDelete = (ruleId: number) => {
    if (confirm('Möchten Sie diese Stellvertretung wirklich löschen?')) {
      deleteMutation.mutate(ruleId);
    }
  };

  const formatDate = (dateStr: string) => {
    try {
      return format(new Date(dateStr), 'dd.MM.yyyy', { locale: de });
    } catch {
      return dateStr;
    }
  };

  const isActive = (startDate: string, endDate: string) => {
    const now = new Date();
    const start = new Date(startDate);
    const end = new Date(endDate);
    return now >= start && now <= end;
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>{UI_LABELS.substitutionRules.title}</CardTitle>
          <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="h-4 w-4 mr-2" />
                {UI_LABELS.substitutionRules.createNew}
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>{UI_LABELS.substitutionRules.createNew}</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 py-4">
                <div className="space-y-2">
                  <Label htmlFor="original-user">
                    {UI_LABELS.substitutionRules.originalUser}
                  </Label>
                  <Input
                    id="original-user"
                    type="number"
                    value={formData.original_user_id}
                    onChange={(e) =>
                      setFormData({ ...formData, original_user_id: Number(e.target.value) })
                    }
                    placeholder="Benutzer-ID"
                  />
                  <p className="text-xs text-muted-foreground">
                    Hinweis: In Produktion würde hier ein Benutzer-Picker verwendet
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="substitute-user">
                    {UI_LABELS.substitutionRules.substituteUser}
                  </Label>
                  <Input
                    id="substitute-user"
                    type="number"
                    value={formData.substitute_user_id}
                    onChange={(e) =>
                      setFormData({ ...formData, substitute_user_id: Number(e.target.value) })
                    }
                    placeholder="Stellvertreter-ID"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="start-date">
                      {UI_LABELS.substitutionRules.startDate}
                    </Label>
                    <Input
                      id="start-date"
                      type="date"
                      value={formData.start_date}
                      onChange={(e) =>
                        setFormData({ ...formData, start_date: e.target.value })
                      }
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="end-date">
                      {UI_LABELS.substitutionRules.endDate}
                    </Label>
                    <Input
                      id="end-date"
                      type="date"
                      value={formData.end_date}
                      onChange={(e) =>
                        setFormData({ ...formData, end_date: e.target.value })
                      }
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="scope">{UI_LABELS.substitutionRules.scope}</Label>
                  <Select
                    value={formData.scope}
                    onValueChange={(value) => setFormData({ ...formData, scope: value })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {SCOPE_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <Separator />

                <div className="flex justify-end gap-2">
                  <Button
                    variant="outline"
                    onClick={() => setIsCreateDialogOpen(false)}
                  >
                    {UI_LABELS.common.cancel}
                  </Button>
                  <Button
                    onClick={handleCreate}
                    disabled={
                      createMutation.isPending ||
                      !formData.start_date ||
                      !formData.end_date
                    }
                  >
                    {createMutation.isPending
                      ? UI_LABELS.common.loading
                      : UI_LABELS.common.create}
                  </Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {[...Array(3)].map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        ) : !rules || rules.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            {UI_LABELS.substitutionRules.noRules}
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{UI_LABELS.substitutionRules.originalUser}</TableHead>
                <TableHead>{UI_LABELS.substitutionRules.substituteUser}</TableHead>
                <TableHead>Zeitraum</TableHead>
                <TableHead>{UI_LABELS.substitutionRules.scope}</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">{UI_LABELS.common.actions}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rules.map((rule) => (
                <TableRow key={rule.id}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <User className="h-4 w-4 text-muted-foreground" />
                      <span>Benutzer #{rule.originalUserId}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <User className="h-4 w-4 text-muted-foreground" />
                      <span>Benutzer #{rule.substituteUserId}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Calendar className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm">
                        {formatDate(rule.startDate)} - {formatDate(rule.endDate)}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{rule.scope}</Badge>
                  </TableCell>
                  <TableCell>
                    {isActive(rule.startDate, rule.endDate) ? (
                      <Badge variant="default">Aktiv</Badge>
                    ) : (
                      <Badge variant="secondary">Inaktiv</Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleDelete(rule.id)}
                      disabled={deleteMutation.isPending}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
