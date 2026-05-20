/**
 * ApprovalRulesPage
 * Tab-based page for conditional rules, escalation, and substitution
 */

import { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Settings2, TrendingUp, Users } from 'lucide-react';
import { ConditionalRuleEditor } from '../components/ConditionalRuleEditor';
import { EscalationRuleList } from '../components/EscalationRuleList';
import { SubstitutionManager } from '../components/SubstitutionManager';
import {
  useConditionalRules,
  useCreateConditionalRule,
  useUpdateConditionalRule,
  useDeleteConditionalRule,
} from '../hooks/use-approval-enhanced-queries';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Plus, Trash2, Edit } from 'lucide-react';
import { UI_LABELS } from '../types/approval-enhanced-types';

export function ApprovalRulesPage() {
  const [activeTab, setActiveTab] = useState('conditional');
  const [isCreating, setIsCreating] = useState(false);
  const [editingRuleId, setEditingRuleId] = useState<number | null>(null);

  const { data: conditionalRules, isLoading } = useConditionalRules();
  const createMutation = useCreateConditionalRule();
  const updateMutation = useUpdateConditionalRule();
  const deleteMutation = useDeleteConditionalRule();

  const handleCreate = (data: {
    name: string;
    conditions: Record<string, unknown>;
    actions: Record<string, unknown>;
    priority: number;
    is_active: boolean;
  }) => {
    createMutation.mutate(data, {
      onSuccess: () => {
        setIsCreating(false);
      },
    });
  };

  const handleUpdate = (data: {
    name: string;
    conditions: Record<string, unknown>;
    actions: Record<string, unknown>;
    priority: number;
    is_active: boolean;
  }) => {
    if (editingRuleId) {
      updateMutation.mutate(
        { ruleId: editingRuleId, data },
        {
          onSuccess: () => {
            setEditingRuleId(null);
          },
        }
      );
    }
  };

  const handleDelete = (ruleId: number) => {
    if (confirm('Möchten Sie diese bedingte Regel wirklich löschen?')) {
      deleteMutation.mutate(ruleId);
    }
  };

  const editingRule = conditionalRules?.find((r) => r.id === editingRuleId);

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Genehmigungsregeln</h1>
        <p className="text-muted-foreground">
          Bedingte Regeln, Eskalation und Stellvertretung
        </p>
      </div>

      <Separator />

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="conditional" className="flex items-center gap-2">
            <Settings2 className="h-4 w-4" />
            Bedingte Regeln
          </TabsTrigger>
          <TabsTrigger value="escalation" className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4" />
            Eskalation
          </TabsTrigger>
          <TabsTrigger value="substitution" className="flex items-center gap-2">
            <Users className="h-4 w-4" />
            Stellvertretung
          </TabsTrigger>
        </TabsList>

        {/* Conditional Rules Tab */}
        <TabsContent value="conditional" className="space-y-4 mt-6">
          {isCreating || editingRuleId ? (
            <ConditionalRuleEditor
              initialName={editingRule?.name}
              initialPriority={editingRule?.priority}
              initialIsActive={editingRule?.isActive}
              onSave={editingRuleId ? handleUpdate : handleCreate}
              onCancel={() => {
                setIsCreating(false);
                setEditingRuleId(null);
              }}
              isLoading={createMutation.isPending || updateMutation.isPending}
            />
          ) : (
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>{UI_LABELS.conditionalRules.title}</CardTitle>
                    <CardDescription>
                      If-then-Regeln für automatisierte Genehmigungen
                    </CardDescription>
                  </div>
                  <Button onClick={() => setIsCreating(true)}>
                    <Plus className="h-4 w-4 mr-2" />
                    {UI_LABELS.conditionalRules.createNew}
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {isLoading ? (
                  <div className="space-y-2">
                    {[...Array(3)].map((_, i) => (
                      <Skeleton key={i} className="h-16 w-full" />
                    ))}
                  </div>
                ) : !conditionalRules || conditionalRules.length === 0 ? (
                  <div className="text-center py-12 text-muted-foreground">
                    {UI_LABELS.conditionalRules.noRules}
                  </div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{UI_LABELS.conditionalRules.name}</TableHead>
                        <TableHead>{UI_LABELS.conditionalRules.priority}</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead className="text-right">
                          {UI_LABELS.common.actions}
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {conditionalRules.map((rule) => (
                        <TableRow key={rule.id}>
                          <TableCell className="font-medium">{rule.name}</TableCell>
                          <TableCell>
                            <Badge variant="outline">{rule.priority}</Badge>
                          </TableCell>
                          <TableCell>
                            {rule.isActive ? (
                              <Badge variant="default">Aktiv</Badge>
                            ) : (
                              <Badge variant="secondary">Inaktiv</Badge>
                            )}
                          </TableCell>
                          <TableCell className="text-right space-x-2">
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => setEditingRuleId(rule.id)}
                            >
                              <Edit className="h-4 w-4" />
                            </Button>
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
          )}
        </TabsContent>

        {/* Escalation Tab */}
        <TabsContent value="escalation" className="space-y-4 mt-6">
          <EscalationRuleList />
        </TabsContent>

        {/* Substitution Tab */}
        <TabsContent value="substitution" className="space-y-4 mt-6">
          <SubstitutionManager />
        </TabsContent>
      </Tabs>
    </div>
  );
}
