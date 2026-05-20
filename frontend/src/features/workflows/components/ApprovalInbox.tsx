import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, Loader2, AlertCircle, ChevronDown, ChevronUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/hooks/use-toast';
import { getMyApprovals, voteOnApproval, type ApprovalRequest } from '../api/approval-api';
import { ApprovalTimeline } from './ApprovalTimeline';
import { ApprovalStamp } from './ApprovalStamp';

export function ApprovalInbox() {
  const [statusFilter, setStatusFilter] = useState<string>('pending');
  const [expandedCard, setExpandedCard] = useState<string | null>(null);
  const [voteDialog, setVoteDialog] = useState<{
    open: boolean;
    approvalId: string;
    decision: 'approved' | 'rejected';
  } | null>(null);
  const [comment, setComment] = useState('');
  const [showStamp, setShowStamp] = useState<{
    approvalId: string;
    decision: 'approved' | 'rejected';
    approverName: string;
    date: string;
  } | null>(null);

  const { toast } = useToast();
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ['my-approvals', statusFilter],
    queryFn: () => getMyApprovals(statusFilter),
    refetchInterval: 30000,
  });

  const voteMutation = useMutation({
    mutationFn: ({ id, decision, comment }: { id: string; decision: 'approved' | 'rejected'; comment?: string }) =>
      voteOnApproval(id, decision, comment),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['my-approvals'] });
      const approval = data?.items.find((a) => a.id === variables.id);
      if (approval) {
        setShowStamp({
          approvalId: variables.id,
          decision: variables.decision,
          approverName: 'Aktueller Benutzer',
          date: new Date().toISOString(),
        });
        setTimeout(() => setShowStamp(null), 3000);
      }
      toast({
        title: variables.decision === 'approved' ? 'Genehmigt' : 'Abgelehnt',
        description: 'Ihre Entscheidung wurde erfolgreich gespeichert.',
      });
      setVoteDialog(null);
      setComment('');
    },
    onError: (err) => {
      toast({
        title: 'Fehler',
        description: 'Die Freigabe konnte nicht verarbeitet werden.',
        variant: 'destructive',
      });
    },
  });

  const handleVoteClick = (approvalId: string, decision: 'approved' | 'rejected') => {
    setVoteDialog({ open: true, approvalId, decision });
  };

  const handleVoteSubmit = () => {
    if (!voteDialog) return;
    voteMutation.mutate({
      id: voteDialog.approvalId,
      decision: voteDialog.decision,
      comment: comment.trim() || undefined,
    });
  };

  const formatCurrency = (amount: number | null): string => {
    if (amount === null) return '';
    return amount.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' });
  };

  const getSLAStatus = (deadline: string | null): { text: string; color: string; isOverdue: boolean } => {
    if (!deadline) return { text: '', color: 'text-muted-foreground', isOverdue: false };

    const now = new Date();
    const sla = new Date(deadline);
    const diffMs = sla.getTime() - now.getTime();
    const diffDays = diffMs / (1000 * 60 * 60 * 24);

    if (diffDays < 0) {
      return { text: 'Überfällig!', color: 'text-red-600', isOverdue: true };
    } else if (diffDays < 1) {
      const hours = Math.floor(diffMs / (1000 * 60 * 60));
      return { text: `${hours}h verbleibend`, color: 'text-yellow-600', isOverdue: false };
    } else if (diffDays < 2) {
      return { text: `${Math.floor(diffDays)} Tag verbleibend`, color: 'text-yellow-600', isOverdue: false };
    } else {
      return { text: `${Math.floor(diffDays)} Tage verbleibend`, color: 'text-green-600', isOverdue: false };
    }
  };

  const pendingCount = data?.items.filter((a) => a.status === 'pending').length || 0;

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="text-center">
          <AlertCircle className="mx-auto h-12 w-12 text-red-500" />
          <p className="mt-4 text-lg font-semibold">Fehler beim Laden</p>
          <p className="text-sm text-muted-foreground">Die Freigaben konnten nicht geladen werden.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-3xl font-bold">Meine Freigaben</h1>
          {pendingCount > 0 && (
            <Badge variant="destructive" className="text-sm">
              {pendingCount}
            </Badge>
          )}
        </div>

        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle</SelectItem>
            <SelectItem value="pending">Ausstehend</SelectItem>
            <SelectItem value="approved">Genehmigt</SelectItem>
            <SelectItem value="rejected">Abgelehnt</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {data?.items.length === 0 ? (
        <div className="flex h-96 items-center justify-center">
          <div className="text-center">
            <CheckCircle2 className="mx-auto h-16 w-16 text-green-500" />
            <p className="mt-4 text-lg font-semibold">Keine ausstehenden Freigaben - alles erledigt!</p>
          </div>
        </div>
      ) : (
        <div className="grid gap-6 md:grid-cols-1 lg:grid-cols-2">
          {data?.items.map((approval: ApprovalRequest) => {
            const slaStatus = getSLAStatus(approval.sla_deadline);
            const isExpanded = expandedCard === approval.id;
            const isStampShowing = showStamp?.approvalId === approval.id;

            return (
              <Card key={approval.id} className="relative">
                <CardHeader>
                  <CardTitle className="flex items-start justify-between gap-2">
                    <span className="flex-1">{approval.document_name}</span>
                    <Badge variant="outline">{approval.document_type}</Badge>
                  </CardTitle>
                  <CardDescription>{approval.workflow_name}</CardDescription>
                </CardHeader>
                <CardContent>
                  {approval.amount && (
                    <div className="mb-3 text-lg font-semibold">{formatCurrency(approval.amount)}</div>
                  )}

                  <div className="mb-3 text-sm text-muted-foreground">
                    Angefragt von: {approval.requester_name}
                  </div>

                  {approval.sla_deadline && (
                    <div className="mb-4 flex items-center gap-2">
                      <span className={`text-sm font-medium ${slaStatus.color}`}>{slaStatus.text}</span>
                      {slaStatus.isOverdue && <Badge variant="destructive">Überfällig!</Badge>}
                    </div>
                  )}

                  {isStampShowing && showStamp && (
                    <div className="mb-4">
                      <ApprovalStamp
                        status={showStamp.decision}
                        approverName={showStamp.approverName}
                        date={showStamp.date}
                        stepNumber={approval.current_step}
                        totalSteps={approval.total_steps}
                      />
                    </div>
                  )}

                  <div className="mb-4 flex flex-wrap gap-2">
                    {approval.status === 'pending' && (
                      <>
                        <Button
                          onClick={() => handleVoteClick(approval.id, 'approved')}
                          size="sm"
                          className="bg-green-600 hover:bg-green-700"
                          disabled={voteMutation.isPending}
                        >
                          {voteMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Genehmigen'}
                        </Button>
                        <Button
                          onClick={() => handleVoteClick(approval.id, 'rejected')}
                          size="sm"
                          variant="outline"
                          className="border-red-600 text-red-600 hover:bg-red-50"
                          disabled={voteMutation.isPending}
                        >
                          Ablehnen
                        </Button>
                      </>
                    )}
                    <Button onClick={() => setExpandedCard(isExpanded ? null : approval.id)} size="sm" variant="ghost">
                      {isExpanded ? (
                        <>
                          <ChevronUp className="mr-1 h-4 w-4" />
                          Weniger
                        </>
                      ) : (
                        <>
                          <ChevronDown className="mr-1 h-4 w-4" />
                          Details
                        </>
                      )}
                    </Button>
                  </div>

                  {isExpanded && (
                    <div className="mt-4 rounded-lg border bg-muted/50 p-4">
                      <h4 className="mb-3 font-semibold">Freigabe-Verlauf</h4>
                      <ApprovalTimeline steps={approval.approval_chain} />
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {voteDialog && (
        <Dialog open={voteDialog.open} onOpenChange={(open) => !open && setVoteDialog(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>
                {voteDialog.decision === 'approved' ? 'Freigabe genehmigen' : 'Freigabe ablehnen'}
              </DialogTitle>
              <DialogDescription>
                Sie können optional einen Kommentar hinzufügen, um Ihre Entscheidung zu begründen.
              </DialogDescription>
            </DialogHeader>
            <div className="py-4">
              <Textarea
                placeholder="Kommentar (optional)..."
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                rows={4}
              />
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setVoteDialog(null)} disabled={voteMutation.isPending}>
                Abbrechen
              </Button>
              <Button
                onClick={handleVoteSubmit}
                disabled={voteMutation.isPending}
                className={
                  voteDialog.decision === 'approved' ? 'bg-green-600 hover:bg-green-700' : 'bg-red-600 hover:bg-red-700'
                }
              >
                {voteMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Bestätigen'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
