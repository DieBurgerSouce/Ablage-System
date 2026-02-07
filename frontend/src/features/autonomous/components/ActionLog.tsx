/**
 * Action Log Component
 * Shows history of all proposals with filtering and rollback capability
 */

import { useState } from 'react';
import { Activity, RotateCcw, Filter } from 'lucide-react';
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
import { cn } from '@/lib/utils';
import { useProposalHistory, useRollbackProposal } from '../hooks/useAutonomous';
import type { ProposalType, ProposalStatus } from '../types/autonomous-types';

const PROPOSAL_TYPE_LABELS: Record<ProposalType, string> = {
  file_document: 'Dokument ablegen',
  approve_payment: 'Zahlung freigeben',
  send_dunning: 'Mahnung senden',
  update_master_data: 'Stammdaten aktualisieren',
  assign_entity: 'Entität zuordnen',
  classify_document: 'Dokument klassifizieren',
};

const STATUS_LABELS: Record<ProposalStatus, string> = {
  pending: 'Ausstehend',
  approved: 'Genehmigt',
  rejected: 'Abgelehnt',
  auto_accepted: 'Auto-Akzeptiert',
  expired: 'Abgelaufen',
  rolled_back: 'Zurückgerollt',
  cancelled: 'Abgebrochen',
};

const STATUS_VARIANTS: Record<
  ProposalStatus,
  'default' | 'secondary' | 'destructive' | 'outline'
> = {
  pending: 'outline',
  approved: 'default',
  rejected: 'destructive',
  auto_accepted: 'default',
  expired: 'secondary',
  rolled_back: 'secondary',
  cancelled: 'secondary',
};

const STATUS_COLORS: Record<ProposalStatus, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  approved: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
  auto_accepted: 'bg-blue-100 text-blue-800',
  expired: 'bg-gray-100 text-gray-800',
  rolled_back: 'bg-orange-100 text-orange-800',
  cancelled: 'bg-gray-100 text-gray-800',
};

export function ActionLog() {
  const [filterType, setFilterType] = useState<string>('all');
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [days, setDays] = useState<string>('30');

  const { data: history, isLoading } = useProposalHistory({
    proposal_type: filterType === 'all' ? undefined : (filterType as ProposalType),
    status: filterStatus === 'all' ? undefined : (filterStatus as ProposalStatus),
    days: parseInt(days, 10),
    limit: 100,
  });

  const rollbackProposal = useRollbackProposal();

  const handleRollback = (proposalId: string) => {
    if (
      window.confirm(
        'Sind Sie sicher, dass Sie diese Aktion rückgängig machen möchten? Dies kann nicht rückgängig gemacht werden.'
      )
    ) {
      rollbackProposal.mutate(proposalId);
    }
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Aktionsverlauf
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
            <Activity className="h-5 w-5" />
            Aktionsverlauf ({history?.length || 0})
          </CardTitle>
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <Select value={filterType} onValueChange={setFilterType}>
              <SelectTrigger className="w-[180px]" aria-label="Nach Typ filtern">
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
            <Select value={filterStatus} onValueChange={setFilterStatus}>
              <SelectTrigger className="w-[160px]" aria-label="Nach Status filtern">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Alle Status</SelectItem>
                <SelectItem value="approved">Genehmigt</SelectItem>
                <SelectItem value="rejected">Abgelehnt</SelectItem>
                <SelectItem value="auto_accepted">Auto-Akzeptiert</SelectItem>
                <SelectItem value="rolled_back">Zurückgerollt</SelectItem>
              </SelectContent>
            </Select>
            <Select value={days} onValueChange={setDays}>
              <SelectTrigger className="w-[120px]" aria-label="Zeitraum auswählen">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="7">7 Tage</SelectItem>
                <SelectItem value="30">30 Tage</SelectItem>
                <SelectItem value="90">90 Tage</SelectItem>
                <SelectItem value="365">1 Jahr</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {!history || history.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            Keine Einträge gefunden
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Datum</TableHead>
                  <TableHead>Typ</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Konfidenz</TableHead>
                  <TableHead>Ausführung</TableHead>
                  <TableHead>Aktionen</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {history.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell className="text-sm">
                      {new Date(entry.created_at).toLocaleString('de-DE', {
                        dateStyle: 'short',
                        timeStyle: 'short',
                      })}
                    </TableCell>
                    <TableCell>
                      <div className="text-sm">
                        {PROPOSAL_TYPE_LABELS[entry.proposal_type]}
                      </div>
                      <div className="text-xs text-muted-foreground font-mono">
                        {entry.target_id}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={STATUS_VARIANTS[entry.status]}
                        className={cn('font-normal', STATUS_COLORS[entry.status])}
                      >
                        {STATUS_LABELS[entry.status]}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm font-medium">
                        {Math.round(entry.confidence * 100)}%
                      </span>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {entry.executed_at
                        ? new Date(entry.executed_at).toLocaleString('de-DE', {
                            dateStyle: 'short',
                            timeStyle: 'short',
                          })
                        : '-'}
                    </TableCell>
                    <TableCell>
                      {entry.can_rollback && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleRollback(entry.id)}
                          disabled={rollbackProposal.isPending}
                          aria-label="Aktion zurückrollen"
                        >
                          <RotateCcw className="h-3 w-3 mr-1" />
                          Zurückrollen
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
