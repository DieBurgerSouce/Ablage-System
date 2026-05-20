/**
 * Delayed Acceptance Queue Component
 * Shows pending proposals awaiting approval or auto-acceptance
 */

import { useState } from 'react';
import { Clock, CheckCircle2, XCircle, AlertTriangle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
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
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import {
  usePendingApprovals,
  useApproveProposal,
  useRejectProposal,
} from '../hooks/useAutonomous';
import type { ProposalType, PendingApprovalResponse } from '../types/autonomous-types';

const PROPOSAL_TYPE_LABELS: Record<ProposalType, string> = {
  file_document: 'Dokument ablegen',
  approve_payment: 'Zahlung freigeben',
  send_dunning: 'Mahnung senden',
  update_master_data: 'Stammdaten aktualisieren',
  assign_entity: 'Entität zuordnen',
  classify_document: 'Dokument klassifizieren',
};

const PROPOSAL_TYPE_COLORS: Record<ProposalType, string> = {
  file_document: 'bg-blue-100 text-blue-800',
  approve_payment: 'bg-green-100 text-green-800',
  send_dunning: 'bg-red-100 text-red-800',
  update_master_data: 'bg-yellow-100 text-yellow-800',
  assign_entity: 'bg-purple-100 text-purple-800',
  classify_document: 'bg-indigo-100 text-indigo-800',
};

function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.9) return 'text-green-600';
  if (confidence >= 0.75) return 'text-yellow-600';
  return 'text-orange-600';
}

function formatTimeRemaining(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return '-';
  if (hours < 0) return 'Abgelaufen';
  if (hours < 1) return `${Math.round(hours * 60)} Minuten`;
  return `${Math.round(hours)} Stunden`;
}

export function DelayedAcceptanceQueue() {
  const [filterType, setFilterType] = useState<string>('all');
  const { data: proposals, isLoading } = usePendingApprovals(
    filterType === 'all' ? {} : { proposal_type: filterType as ProposalType }
  );
  const approveProposal = useApproveProposal();
  const rejectProposal = useRejectProposal();

  const handleApprove = (proposalId: string) => {
    approveProposal.mutate(proposalId);
  };

  const handleReject = (proposalId: string) => {
    const reason = window.prompt('Grund für die Ablehnung (optional):');
    rejectProposal.mutate({
      proposalId,
      data: reason ? { reason } : undefined,
    });
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Clock className="h-5 w-5" />
            Warteschlange
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">Lädt...</div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Clock className="h-5 w-5" />
            Warteschlange ({proposals?.length || 0})
          </CardTitle>
          <Select value={filterType} onValueChange={setFilterType}>
            <SelectTrigger className="w-[200px]" aria-label="Vorschlagstyp filtern">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle Typen</SelectItem>
              <SelectItem value="file_document">Dokument ablegen</SelectItem>
              <SelectItem value="approve_payment">Zahlung freigeben</SelectItem>
              <SelectItem value="send_dunning">Mahnung senden</SelectItem>
              <SelectItem value="update_master_data">Stammdaten aktualisieren</SelectItem>
              <SelectItem value="assign_entity">Entität zuordnen</SelectItem>
              <SelectItem value="classify_document">Dokument klassifizieren</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </CardHeader>
      <CardContent>
        {!proposals || proposals.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            Keine ausstehenden Vorschläge
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Typ</TableHead>
                  <TableHead>Ziel-ID</TableHead>
                  <TableHead>Konfidenz</TableHead>
                  <TableHead>Verbleibende Zeit</TableHead>
                  <TableHead>Erstellt</TableHead>
                  <TableHead>Aktionen</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {proposals.map((proposal) => (
                  <TableRow key={proposal.id}>
                    <TableCell>
                      <Badge
                        variant="secondary"
                        className={cn('font-normal', PROPOSAL_TYPE_COLORS[proposal.proposal_type])}
                      >
                        {PROPOSAL_TYPE_LABELS[proposal.proposal_type]}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs">{proposal.target_id}</TableCell>
                    <TableCell>
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <Progress value={proposal.confidence * 100} className="w-20" />
                          <span
                            className={cn(
                              'text-sm font-medium',
                              getConfidenceColor(proposal.confidence)
                            )}
                          >
                            {Math.round(proposal.confidence * 100)}%
                          </span>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {proposal.time_remaining_hours !== undefined &&
                        proposal.time_remaining_hours < 1 ? (
                          <AlertTriangle className="h-4 w-4 text-orange-600" />
                        ) : (
                          <Clock className="h-4 w-4 text-muted-foreground" />
                        )}
                        <span className="text-sm">
                          {formatTimeRemaining(proposal.time_remaining_hours)}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {new Date(proposal.created_at).toLocaleString('de-DE')}
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant="default"
                          onClick={() => handleApprove(proposal.id)}
                          disabled={approveProposal.isPending || rejectProposal.isPending}
                          aria-label="Vorschlag genehmigen"
                        >
                          <CheckCircle2 className="h-4 w-4 mr-1" />
                          Genehmigen
                        </Button>
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => handleReject(proposal.id)}
                          disabled={approveProposal.isPending || rejectProposal.isPending}
                          aria-label="Vorschlag ablehnen"
                        >
                          <XCircle className="h-4 w-4 mr-1" />
                          Ablehnen
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        {proposals && proposals.length > 0 && (
          <div className="mt-4 text-xs text-muted-foreground">
            Vorschläge werden nach Ablauf der Wartezeit automatisch akzeptiert, sofern die
            Vertrauensstufe dies zulässt.
          </div>
        )}
      </CardContent>
    </Card>
  );
}
