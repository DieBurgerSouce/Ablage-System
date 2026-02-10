/**
 * POMatchDetail - Detailansicht eines PO-Matches
 *
 * Zeigt:
 * - Header mit Bestellnummer, Lieferant, Status, Match-Score
 * - 3-Spalten-Vergleich: Bestellung | Lieferschein | Rechnung
 * - Abweichungen-Tabelle mit Schweregrad-Badges
 * - Aktionen: Freigeben (mit Bestaetigung), Bewerten, Zurueck
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
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  ArrowLeft,
  CheckCircle2,
  RefreshCw,
  Loader2,
  FileText,
  Truck,
  Receipt,
  AlertTriangle,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { usePOMatch, useApprovePOMatch, useEvaluatePOMatch } from '../hooks/usePOMatching';
import type {
  MatchStatus,
  DiscrepancyCategory,
  DiscrepancySeverity,
} from '../types/po-matching-types';

// ==================== Props ====================

interface POMatchDetailProps {
  matchId: string;
  onBack: () => void;
}

// ==================== Helpers ====================

const STATUS_CONFIG: Record<
  MatchStatus,
  { label: string; className: string }
> = {
  pending: {
    label: 'Ausstehend',
    className: 'bg-gray-100 text-gray-800 border-gray-200',
  },
  partial: {
    label: 'Teilweise',
    className: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  },
  full: {
    label: 'Vollstaendig',
    className: 'bg-green-100 text-green-800 border-green-200',
  },
  discrepancy: {
    label: 'Abweichung',
    className: 'bg-red-100 text-red-800 border-red-200',
  },
  rejected: {
    label: 'Abgelehnt',
    className: 'bg-destructive text-destructive-foreground',
  },
  approved: {
    label: 'Freigegeben',
    className: 'bg-green-600 text-white border-green-700',
  },
};

const SEVERITY_CONFIG: Record<
  DiscrepancySeverity,
  { label: string; className: string }
> = {
  info: {
    label: 'Info',
    className: 'bg-blue-100 text-blue-800 border-blue-200',
  },
  warning: {
    label: 'Warnung',
    className: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  },
  error: {
    label: 'Fehler',
    className: 'bg-red-100 text-red-800 border-red-200',
  },
  critical: {
    label: 'Kritisch',
    className: 'bg-red-600 text-white border-red-700',
  },
};

const CATEGORY_LABELS: Record<DiscrepancyCategory, string> = {
  amount: 'Betrag',
  quantity: 'Menge',
  item: 'Artikel',
  date: 'Datum',
  price: 'Preis',
};

function formatEUR(value: number | null): string {
  if (value === null || value === undefined) return '-';
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(value);
}

function formatDate(isoDate: string | null): string {
  if (!isoDate) return '-';
  return new Intl.DateTimeFormat('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(isoDate));
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return '-';
  return `${value.toFixed(1)}%`;
}

// ==================== Component ====================

export function POMatchDetail({ matchId, onBack }: POMatchDetailProps) {
  const { data: match, isLoading } = usePOMatch(matchId);
  const approve = useApprovePOMatch();
  const evaluate = useEvaluatePOMatch();
  const [approveDialogOpen, setApproveDialogOpen] = useState(false);

  function handleApprove() {
    approve.mutate(
      { matchId },
      {
        onSuccess: () => {
          setApproveDialogOpen(false);
        },
      }
    );
  }

  function handleEvaluate() {
    evaluate.mutate(matchId);
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!match) {
    return (
      <div className="text-center py-24 text-muted-foreground">
        <p className="text-lg">Match nicht gefunden</p>
        <Button variant="outline" className="mt-4" onClick={onBack}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Zurueck zur Liste
        </Button>
      </div>
    );
  }

  const statusCfg = STATUS_CONFIG[match.match_status];
  const discrepancies = match.discrepancies ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={onBack}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Zurueck
          </Button>
          <div>
            <h2 className="text-2xl font-bold tracking-tight">
              {match.order_number
                ? `Bestellung ${match.order_number}`
                : `Match ${match.id.slice(0, 8)}...`}
            </h2>
            <p className="text-muted-foreground mt-1">
              {match.vendor_name || 'Unbekannter Lieferant'}
              {match.order_date && ` - ${formatDate(match.order_date)}`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Badge
            variant="outline"
            className={cn('text-sm px-3 py-1', statusCfg.className)}
          >
            {statusCfg.label}
          </Badge>
          <div className="text-right">
            <p className="text-xs text-muted-foreground">Match-Score</p>
            <div className="flex items-center gap-2 mt-1">
              <div className="w-24 h-2 bg-muted rounded-full overflow-hidden">
                <div
                  className={cn(
                    'h-full rounded-full transition-all',
                    match.match_score >= 80
                      ? 'bg-green-500'
                      : match.match_score >= 50
                        ? 'bg-yellow-500'
                        : 'bg-red-500'
                  )}
                  style={{ width: `${Math.min(100, match.match_score)}%` }}
                />
              </div>
              <span className="text-sm font-semibold tabular-nums">
                {formatPercent(match.match_score)}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* 3-Spalten Vergleich */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Bestellung */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <FileText className="h-4 w-4 text-blue-600" />
              Bestellung
            </CardTitle>
            <CardDescription>Purchase Order</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <p className="text-xs text-muted-foreground">Dokument-ID</p>
              <p className="text-sm font-mono">
                {match.purchase_order_id
                  ? match.purchase_order_id.slice(0, 8) + '...'
                  : 'Nicht verknuepft'}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Betrag</p>
              <p className="text-lg font-semibold tabular-nums">
                {formatEUR(match.po_amount)}
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Lieferschein */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Truck className="h-4 w-4 text-orange-600" />
              Lieferschein
            </CardTitle>
            <CardDescription>Delivery Note</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <p className="text-xs text-muted-foreground">Dokument-ID</p>
              <p className="text-sm font-mono">
                {match.delivery_note_id
                  ? match.delivery_note_id.slice(0, 8) + '...'
                  : 'Nicht verknuepft'}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Betrag</p>
              <p className="text-lg font-semibold tabular-nums">
                {formatEUR(match.dn_amount)}
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Rechnung */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Receipt className="h-4 w-4 text-green-600" />
              Rechnung
            </CardTitle>
            <CardDescription>Invoice</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <p className="text-xs text-muted-foreground">Dokument-ID</p>
              <p className="text-sm font-mono">
                {match.invoice_id
                  ? match.invoice_id.slice(0, 8) + '...'
                  : 'Nicht verknuepft'}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Betrag</p>
              <p className="text-lg font-semibold tabular-nums">
                {formatEUR(match.invoice_amount)}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Match-Details Karte */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Match-Details</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <p className="text-muted-foreground">Dokumente</p>
              <p className="font-medium">{match.document_count} / 3</p>
            </div>
            <div>
              <p className="text-muted-foreground">Vollstaendig</p>
              <p className="font-medium">{match.is_complete ? 'Ja' : 'Nein'}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Auto-Match</p>
              <p className="font-medium">
                {match.auto_matched ? 'Ja' : 'Manuell'}
              </p>
            </div>
            <div>
              <p className="text-muted-foreground">Toleranz (Betrag/Menge)</p>
              <p className="font-medium tabular-nums">
                {match.amount_tolerance_percent}% / {match.quantity_tolerance_percent}%
              </p>
            </div>
            {match.approved_at && (
              <>
                <div>
                  <p className="text-muted-foreground">Freigegeben am</p>
                  <p className="font-medium">{formatDate(match.approved_at)}</p>
                </div>
                {match.approval_notes && (
                  <div className="col-span-2">
                    <p className="text-muted-foreground">Freigabe-Notizen</p>
                    <p className="font-medium">{match.approval_notes}</p>
                  </div>
                )}
              </>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Abweichungen */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <AlertTriangle className="h-4 w-4" />
            Abweichungen ({discrepancies.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {discrepancies.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">
              Keine Abweichungen erkannt.
            </p>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Kategorie</TableHead>
                    <TableHead>Beschreibung</TableHead>
                    <TableHead className="text-right">Erwartet</TableHead>
                    <TableHead className="text-right">Tatsaechlich</TableHead>
                    <TableHead className="text-right">Abweichung</TableHead>
                    <TableHead>Schweregrad</TableHead>
                    <TableHead className="text-center">Geloest</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {discrepancies.map((d) => {
                    const sevCfg = SEVERITY_CONFIG[d.severity];

                    return (
                      <TableRow key={d.id}>
                        <TableCell className="font-medium">
                          {CATEGORY_LABELS[d.category] ?? d.category}
                        </TableCell>
                        <TableCell className="max-w-xs truncate">
                          {d.description}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {d.expected_amount !== null
                            ? formatEUR(d.expected_amount)
                            : d.expected_value ?? '-'}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {d.actual_amount !== null
                            ? formatEUR(d.actual_amount)
                            : d.actual_value ?? '-'}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {formatPercent(d.deviation_percent)}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant="outline"
                            className={cn('text-xs', sevCfg.className)}
                          >
                            {sevCfg.label}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-center">
                          {d.resolved ? (
                            <CheckCircle2 className="h-4 w-4 text-green-600 mx-auto" />
                          ) : (
                            <span className="text-muted-foreground">-</span>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Aktionen */}
      <div className="flex items-center gap-3">
        <Button
          variant="outline"
          onClick={handleEvaluate}
          disabled={evaluate.isPending}
        >
          {evaluate.isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="mr-2 h-4 w-4" />
          )}
          Bewerten
        </Button>

        <Dialog open={approveDialogOpen} onOpenChange={setApproveDialogOpen}>
          <DialogTrigger asChild>
            <Button
              disabled={
                match.match_status === 'approved' ||
                match.match_status === 'rejected' ||
                approve.isPending
              }
            >
              <CheckCircle2 className="mr-2 h-4 w-4" />
              Freigeben
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Match freigeben</DialogTitle>
              <DialogDescription>
                Moechten Sie diesen Match wirklich freigeben?
                {discrepancies.filter((d) => !d.resolved).length > 0 && (
                  <span className="block mt-2 text-yellow-600 font-medium">
                    Achtung: Es gibt noch{' '}
                    {discrepancies.filter((d) => !d.resolved).length} ungeloeste
                    Abweichung(en).
                  </span>
                )}
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setApproveDialogOpen(false)}
              >
                Abbrechen
              </Button>
              <Button
                onClick={handleApprove}
                disabled={approve.isPending}
              >
                {approve.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="mr-2 h-4 w-4" />
                )}
                Freigabe bestaetigen
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}
