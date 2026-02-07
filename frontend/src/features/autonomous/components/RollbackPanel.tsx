/**
 * Rollback Panel Component
 * Shows proposals eligible for rollback with countdown timers
 */

import { RotateCcw, Clock, AlertTriangle } from 'lucide-react';
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
import { cn } from '@/lib/utils';
import { useProposalHistory, useRollbackProposal } from '../hooks/useAutonomous';
import type { ProposalType } from '../types/autonomous-types';

const PROPOSAL_TYPE_LABELS: Record<ProposalType, string> = {
  file_document: 'Dokument ablegen',
  approve_payment: 'Zahlung freigeben',
  send_dunning: 'Mahnung senden',
  update_master_data: 'Stammdaten aktualisieren',
  assign_entity: 'Entität zuordnen',
  classify_document: 'Dokument klassifizieren',
};

function getRollbackTimeRemaining(rollbackUntil: string): {
  hours: number;
  isExpiringSoon: boolean;
  formatted: string;
} {
  const now = new Date();
  const until = new Date(rollbackUntil);
  const msRemaining = until.getTime() - now.getTime();
  const hoursRemaining = msRemaining / (1000 * 60 * 60);

  if (hoursRemaining < 0) {
    return { hours: 0, isExpiringSoon: true, formatted: 'Abgelaufen' };
  }

  if (hoursRemaining < 1) {
    const minutes = Math.round(hoursRemaining * 60);
    return {
      hours: hoursRemaining,
      isExpiringSoon: true,
      formatted: `${minutes} Minuten`,
    };
  }

  return {
    hours: hoursRemaining,
    isExpiringSoon: hoursRemaining < 24,
    formatted: `${Math.round(hoursRemaining)} Stunden`,
  };
}

export function RollbackPanel() {
  const { data: history, isLoading } = useProposalHistory({
    status: 'approved',
    days: 7,
    limit: 50,
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

  // Filter to only show rollback-eligible proposals
  const rollbackEligible = history?.filter(
    (entry) =>
      entry.can_rollback &&
      entry.rollback_until &&
      new Date(entry.rollback_until) > new Date()
  );

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <RotateCcw className="h-5 w-5" />
            Rollback-Optionen
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
        <CardTitle className="flex items-center gap-2">
          <RotateCcw className="h-5 w-5" />
          Rollback-Optionen ({rollbackEligible?.length || 0})
        </CardTitle>
      </CardHeader>
      <CardContent>
        {!rollbackEligible || rollbackEligible.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            Keine Aktionen können aktuell zurückgerollt werden
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <AlertTriangle className="h-4 w-4" />
              <span>
                Rollback-Zeitfenster läuft ab. Aktionen können nur innerhalb des angegebenen
                Zeitraums rückgängig gemacht werden.
              </span>
            </div>

            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Typ</TableHead>
                    <TableHead>Ziel-ID</TableHead>
                    <TableHead>Ausgeführt am</TableHead>
                    <TableHead>Verbleibende Zeit</TableHead>
                    <TableHead>Aktionen</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rollbackEligible.map((entry) => {
                    const timeInfo = getRollbackTimeRemaining(entry.rollback_until!);

                    return (
                      <TableRow key={entry.id}>
                        <TableCell>
                          <div className="text-sm">
                            {PROPOSAL_TYPE_LABELS[entry.proposal_type]}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            Konfidenz: {Math.round(entry.confidence * 100)}%
                          </div>
                        </TableCell>
                        <TableCell className="font-mono text-xs">{entry.target_id}</TableCell>
                        <TableCell className="text-sm">
                          {entry.executed_at
                            ? new Date(entry.executed_at).toLocaleString('de-DE', {
                                dateStyle: 'short',
                                timeStyle: 'short',
                              })
                            : '-'}
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            {timeInfo.isExpiringSoon ? (
                              <AlertTriangle className="h-4 w-4 text-orange-600" />
                            ) : (
                              <Clock className="h-4 w-4 text-muted-foreground" />
                            )}
                            <Badge
                              variant={timeInfo.isExpiringSoon ? 'destructive' : 'secondary'}
                              className="font-normal"
                            >
                              {timeInfo.formatted}
                            </Badge>
                          </div>
                        </TableCell>
                        <TableCell>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleRollback(entry.id)}
                            disabled={rollbackProposal.isPending}
                            className={cn(
                              timeInfo.isExpiringSoon &&
                                'border-orange-600 text-orange-600 hover:bg-orange-50'
                            )}
                            aria-label="Aktion zurückrollen"
                          >
                            <RotateCcw className="h-3 w-3 mr-1" />
                            Zurückrollen
                          </Button>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
