/**
 * EscalationRuleList Component
 * Table view for escalation rules with CRUD actions
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
import { Switch } from '@/components/ui/switch';
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
import { Plus, Trash2, Clock } from 'lucide-react';
import {
  useEscalationRules,
  useCreateEscalationRule,
  useDeleteEscalationRule,
} from '../hooks/use-approval-enhanced-queries';
import { UI_LABELS } from '../types/approval-enhanced-types';

export function EscalationRuleList() {
  const { data: rules, isLoading } = useEscalationRules();
  const createMutation = useCreateEscalationRule();
  const deleteMutation = useDeleteEscalationRule();

  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    timeout_hours: 24,
    escalation_target: '',
    notify_original: true,
  });

  const handleCreate = () => {
    createMutation.mutate(formData, {
      onSuccess: () => {
        setIsCreateDialogOpen(false);
        setFormData({
          name: '',
          timeout_hours: 24,
          escalation_target: '',
          notify_original: true,
        });
      },
    });
  };

  const handleDelete = (ruleId: number) => {
    if (confirm('Möchten Sie diese Eskalationsregel wirklich löschen?')) {
      deleteMutation.mutate(ruleId);
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>{UI_LABELS.escalationRules.title}</CardTitle>
          <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="h-4 w-4 mr-2" />
                {UI_LABELS.escalationRules.createNew}
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>{UI_LABELS.escalationRules.createNew}</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 py-4">
                <div className="space-y-2">
                  <Label htmlFor="esc-name">{UI_LABELS.escalationRules.name}</Label>
                  <Input
                    id="esc-name"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    placeholder="z.B. Standard-Eskalation nach 24h"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="timeout">{UI_LABELS.escalationRules.timeoutHours}</Label>
                  <Input
                    id="timeout"
                    type="number"
                    value={formData.timeout_hours}
                    onChange={(e) =>
                      setFormData({ ...formData, timeout_hours: Number(e.target.value) })
                    }
                    min={1}
                    max={168}
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="target">{UI_LABELS.escalationRules.escalationTarget}</Label>
                  <Input
                    id="target"
                    value={formData.escalation_target}
                    onChange={(e) =>
                      setFormData({ ...formData, escalation_target: e.target.value })
                    }
                    placeholder="z.B. manager@firma.de"
                  />
                </div>

                <div className="flex items-center space-x-2">
                  <Switch
                    id="notify"
                    checked={formData.notify_original}
                    onCheckedChange={(checked) =>
                      setFormData({ ...formData, notify_original: checked })
                    }
                  />
                  <Label htmlFor="notify">{UI_LABELS.escalationRules.notifyOriginal}</Label>
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
                      !formData.name.trim() ||
                      !formData.escalation_target.trim()
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
            {UI_LABELS.escalationRules.noRules}
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{UI_LABELS.escalationRules.name}</TableHead>
                <TableHead>{UI_LABELS.escalationRules.timeoutHours}</TableHead>
                <TableHead>{UI_LABELS.escalationRules.escalationTarget}</TableHead>
                <TableHead>{UI_LABELS.escalationRules.notifyOriginal}</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">{UI_LABELS.common.actions}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rules.map((rule) => (
                <TableRow key={rule.id}>
                  <TableCell className="font-medium">{rule.name}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1">
                      <Clock className="h-4 w-4 text-muted-foreground" />
                      <span>{rule.timeoutHours}h</span>
                    </div>
                  </TableCell>
                  <TableCell>{rule.escalationTarget}</TableCell>
                  <TableCell>
                    {rule.notifyOriginal ? (
                      <Badge variant="default">Ja</Badge>
                    ) : (
                      <Badge variant="secondary">Nein</Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    {rule.isActive ? (
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
