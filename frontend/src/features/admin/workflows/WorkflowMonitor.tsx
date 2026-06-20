/**
 * Workflow Monitor Page
 *
 * Admin-Seite für Überwachung von aktiven Approval-Requests.
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Activity, RefreshCw, Loader2, ChevronDown, ChevronRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { toast } from 'sonner';
import { listApprovals, voteOnApproval, type ApprovalStep } from './api/workflow-admin-api';

// Status variants
const STATUS_VARIANTS: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  pending: 'default',
  approved: 'secondary',
  rejected: 'destructive',
  expired: 'outline',
};

export function WorkflowMonitor() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState('pending');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  // Load approvals with auto-refresh
  const {
    data: approvalsData,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ['approvals', statusFilter, dateFrom, dateTo],
    queryFn: () =>
      listApprovals({
        status: statusFilter === 'all' ? undefined : statusFilter,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      }),
    refetchInterval: 30000, // Auto-refresh every 30s
  });

  const approvals = approvalsData?.items || [];

  // Vote mutation
  void useMutation({
    mutationFn: ({
      id,
      decision,
      comment,
    }: {
      id: string;
      decision: 'approved' | 'rejected';
      comment?: string;
    }) => voteOnApproval(id, { decision, comment }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
      toast.success('Abstimmung erfolgreich gespeichert');
    },
    onError: () => {
      toast.error('Fehler beim Speichern der Abstimmung');
    },
  });

  const toggleRow = (id: string) => {
    setExpandedRows((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
  };


  const calculateSLAStatus = (deadline: string | null) => {
    if (!deadline) return { text: '-', color: '' };
    const now = new Date();
    const deadlineDate = new Date(deadline);
    const diff = deadlineDate.getTime() - now.getTime();
    const days = Math.ceil(diff / (1000 * 60 * 60 * 24));

    if (days < 0) {
      return { text: `${Math.abs(days)} Tage überfällig`, color: 'text-red-600 dark:text-red-400' };
    } else if (days === 0) {
      return { text: 'Heute fällig', color: 'text-orange-600 dark:text-orange-400' };
    } else {
      return { text: `${days} Tage verbleibend`, color: 'text-green-600 dark:text-green-400' };
    }
  };

  const calculateConsensus = (chain: ApprovalStep[]) => {
    const total = chain.filter((s) => s.required).length;
    const approved = chain.filter((s) => s.decision === 'approved').length;
    return { approved, total, percent: total > 0 ? (approved / total) * 100 : 0 };
  };

  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-primary/10 rounded-lg">
            <Activity className="h-8 w-8 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">Workflow-Monitor</h1>
            <p className="text-muted-foreground">
              Aktive Genehmigungsanfragen überwachen
            </p>
          </div>
        </div>
        <Button variant="outline" onClick={() => refetch()}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Aktualisieren
        </Button>
      </div>

      {/* Filter Bar */}
      <Card>
        <CardContent className="py-4">
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Alle</SelectItem>
                  <SelectItem value="pending">Ausstehend</SelectItem>
                  <SelectItem value="approved">Genehmigt</SelectItem>
                  <SelectItem value="rejected">Abgelehnt</SelectItem>
                  <SelectItem value="expired">Abgelaufen</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex-1">
              <Input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                placeholder="Von"
              />
            </div>
            <div className="flex-1">
              <Input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                placeholder="Bis"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Approvals Table */}
      <Card>
        <CardHeader>
          <CardTitle>Genehmigungsanfragen ({approvals.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : approvals.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <Activity className="h-12 w-12 text-muted-foreground mb-4" />
              <h3 className="text-lg font-medium">Keine aktiven Genehmigungsanfragen</h3>
              <p className="text-sm text-muted-foreground mt-1">
                Es gibt derzeit keine Genehmigungsanfragen
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[50px]"></TableHead>
                  <TableHead>Dokument</TableHead>
                  <TableHead>Workflow</TableHead>
                  <TableHead>Fortschritt</TableHead>
                  <TableHead>Genehmiger</TableHead>
                  <TableHead>SLA</TableHead>
                  <TableHead>Konsens</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {approvals.map((approval) => {
                  const isExpanded = expandedRows.has(approval.id);
                  const slaStatus = calculateSLAStatus(approval.sla_deadline);
                  const consensus = calculateConsensus(approval.approval_chain);

                  return (
                    <>
                      <TableRow key={approval.id} className="cursor-pointer">
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => toggleRow(approval.id)}
                          >
                            {isExpanded ? (
                              <ChevronDown className="h-4 w-4" />
                            ) : (
                              <ChevronRight className="h-4 w-4" />
                            )}
                          </Button>
                        </TableCell>
                        <TableCell>
                          <div className="font-medium">{approval.document_name}</div>
                          <Badge variant="outline" className="mt-1">
                            {approval.document_type}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <div className="text-sm">{approval.workflow_name}</div>
                        </TableCell>
                        <TableCell>
                          <div className="text-sm">
                            Schritt {approval.current_step} von {approval.total_steps}
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="flex gap-1 flex-wrap">
                            {approval.approval_chain.slice(0, 3).map((step, idx) => (
                              <Badge
                                key={step.step_number || idx}
                                variant={
                                  step.decision === 'approved'
                                    ? 'default'
                                    : step.decision === 'rejected'
                                    ? 'destructive'
                                    : 'secondary'
                                }
                                className={
                                  step.decision === 'approved'
                                    ? 'bg-green-500'
                                    : step.decision === 'rejected'
                                    ? 'bg-red-500'
                                    : ''
                                }
                              >
                                {step.approver_name || step.role}
                              </Badge>
                            ))}
                            {approval.approval_chain.length > 3 && (
                              <Badge variant="outline">
                                +{approval.approval_chain.length - 3}
                              </Badge>
                            )}
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className={`text-sm font-medium ${slaStatus.color}`}>
                            {slaStatus.text}
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="space-y-1">
                            <div className="text-sm">
                              {consensus.approved}/{consensus.total} genehmigt
                            </div>
                            <Progress value={consensus.percent} className="h-2" />
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge variant={STATUS_VARIANTS[approval.status] || 'outline'}>
                            {approval.status === 'pending'
                              ? 'Ausstehend'
                              : approval.status === 'approved'
                              ? 'Genehmigt'
                              : approval.status === 'rejected'
                              ? 'Abgelehnt'
                              : 'Abgelaufen'}
                          </Badge>
                        </TableCell>
                      </TableRow>

                      {/* Expanded Timeline */}
                      {isExpanded && (
                        <TableRow>
                          <TableCell colSpan={8} className="bg-muted/50">
                            <ApprovalTimeline chain={approval.approval_chain} />
                          </TableCell>
                        </TableRow>
                      )}
                    </>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// =============================================================================
// Approval Timeline Component
// =============================================================================

interface ApprovalTimelineProps {
  chain: ApprovalStep[];
}

function ApprovalTimeline({ chain }: ApprovalTimelineProps) {
  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="py-4 px-6 space-y-4">
      <h4 className="font-semibold">Genehmigungsverlauf</h4>
      <div className="space-y-3">
        {chain.map((step, idx) => (
          <div key={step.step_number || idx} className="flex items-start gap-4">
            <div className="flex flex-col items-center">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center ${
                  step.decision === 'approved'
                    ? 'bg-green-500 text-white'
                    : step.decision === 'rejected'
                    ? 'bg-red-500 text-white'
                    : 'bg-gray-300 text-gray-600'
                }`}
              >
                {step.step_number}
              </div>
              {idx < chain.length - 1 && (
                <div className="w-0.5 h-8 bg-gray-300 dark:bg-gray-700"></div>
              )}
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="font-medium">{step.role}</span>
                {step.approver_name && (
                  <span className="text-sm text-muted-foreground">
                    ({step.approver_name})
                  </span>
                )}
                {step.required && (
                  <Badge variant="outline" className="text-xs">
                    Erforderlich
                  </Badge>
                )}
              </div>
              <div className="text-sm text-muted-foreground mt-1">
                {step.decision ? (
                  <>
                    <Badge
                      variant={
                        step.decision === 'approved'
                          ? 'default'
                          : step.decision === 'rejected'
                          ? 'destructive'
                          : 'secondary'
                      }
                      className={
                        step.decision === 'approved' ? 'bg-green-500' : ''
                      }
                    >
                      {step.decision === 'approved'
                        ? 'Genehmigt'
                        : step.decision === 'rejected'
                        ? 'Abgelehnt'
                        : 'Ausstehend'}
                    </Badge>
                    {' am '}
                    {formatDate(step.decided_at)}
                  </>
                ) : (
                  <Badge variant="secondary">Ausstehend</Badge>
                )}
              </div>
              {step.comment && (
                <div className="text-sm mt-2 p-2 bg-background rounded border">
                  {step.comment}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
