/**
 * ThreeWayMatchView - Erweiterte 3-Way-Matching Ansicht
 *
 * Hauptkomponente mit drei Tabs:
 * - "Uebersicht": Erweiterte Liste mit 3-Spalten-Betragsvergleich
 * - "Abgleich": Detail-Ansicht mit visuellem Diff und Abweichungskarten
 * - "Statistiken": Wiederverwendung von POMatchStats
 *
 * Nutzt die bestehenden PO-Matching Hooks und Typen.
 */

import { useState, useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
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
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
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
  Loader2,
  Zap,
  ChevronLeft,
  ChevronRight,
  FileSearch,
  ArrowLeft,
  CheckCircle2,
  RefreshCw,
  FileText,
  Truck,
  Receipt,
  AlertTriangle,
  ArrowRightLeft,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  usePOMatches,
  usePOMatch,
  useAutoMatch,
  useApprovePOMatch,
  useEvaluatePOMatch,
} from '@/features/po-matching/hooks/usePOMatching';
import { POMatchStats } from '@/features/po-matching/components/POMatchStats';
import type {
  MatchStatus,
  MatchResponse,
  POMatchFilter,
} from '@/features/po-matching/types/po-matching-types';
import { MatchScoreBar } from './MatchScoreBar';
import { DiscrepancyCard } from './DiscrepancyCard';

// ==================== Konfiguration ====================

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
    label: 'Vollst\u00e4ndig',
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

// ==================== Hilfsfunktionen ====================

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
  }).format(new Date(isoDate));
}

function formatDateTime(isoDate: string | null): string {
  if (!isoDate) return '-';
  return new Intl.DateTimeFormat('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(isoDate));
}

/**
 * Prueft ob die drei Betraege voneinander abweichen.
 * Gibt true zurueck wenn mindestens zwei nicht-null Werte unterschiedlich sind.
 */
function hasAmountDeviation(match: MatchResponse): boolean {
  const amounts = [match.po_amount, match.dn_amount, match.invoice_amount].filter(
    (a): a is number => a !== null
  );
  if (amounts.length < 2) return false;
  return !amounts.every((a) => a === amounts[0]);
}

// ==================== Props ====================

interface ThreeWayMatchViewProps {
  /** Aktuell aktiver Tab */
  activeTab: string;
  /** Ausgewaehlte Match-ID fuer Detail-Ansicht */
  selectedMatchId?: string;
  /** Callback fuer Tab-Wechsel */
  onTabChange: (tab: string) => void;
  /** Callback fuer Match-Auswahl */
  onSelectMatch: (matchId: string) => void;
  /** Callback fuer Zurueck-Navigation */
  onBack: () => void;
}

// ==================== Uebersicht-Tab ====================

function MatchOverviewTab({
  onSelectMatch,
}: {
  onSelectMatch: (matchId: string) => void;
}) {
  const [page, setPage] = useState(0);
  const [pageSize] = useState(25);

  const filters: POMatchFilter = {
    page,
    page_size: pageSize,
  };

  const { data, isLoading, isFetching } = usePOMatches(filters);
  const autoMatch = useAutoMatch();

  const matches = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const tableContainerRef = useRef<HTMLDivElement>(null);
  const rowVirtualizer = useVirtualizer({
    count: matches.length,
    getScrollElement: () => tableContainerRef.current,
    estimateSize: () => 48,
    overscan: 5,
  });

  const virtualRows = rowVirtualizer.getVirtualItems();
  const totalSize = rowVirtualizer.getTotalSize();
  const paddingTop = virtualRows.length > 0 ? virtualRows[0]?.start ?? 0 : 0;
  const paddingBottom =
    virtualRows.length > 0
      ? totalSize - (virtualRows[virtualRows.length - 1]?.end ?? 0)
      : 0;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
        <div>
          <CardTitle className="text-xl font-semibold">
            3-Way-Matching \u00dcbersicht
          </CardTitle>
          <CardDescription className="mt-1">
            Bestellung, Lieferschein und Rechnung im Vergleich
          </CardDescription>
        </div>
        <Button
          onClick={() => autoMatch.mutate()}
          disabled={autoMatch.isPending}
          size="sm"
        >
          {autoMatch.isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Zap className="mr-2 h-4 w-4" />
          )}
          Auto-Matching
        </Button>
      </CardHeader>

      <CardContent>
        {/* Auto-Match Ergebnis */}
        {autoMatch.isSuccess && (
          <div className="mb-4 rounded-md bg-green-50 p-3 text-sm text-green-800 border border-green-200">
            Auto-Matching abgeschlossen: {autoMatch.data.matches_updated} Matches
            aktualisiert.
          </div>
        )}

        {/* Tabelle */}
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : matches.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <FileSearch className="h-12 w-12 mb-4" />
            <p className="text-lg font-medium">Keine Matches vorhanden</p>
            <p className="text-sm mt-1">
              Starten Sie das Auto-Matching, um Dokumente abzugleichen.
            </p>
          </div>
        ) : (
          <>
            <div
              ref={tableContainerRef}
              className="rounded-md border overflow-auto max-h-[600px]"
            >
              <Table>
                <TableHeader className="sticky top-0 z-10 bg-background shadow-sm">
                  <TableRow>
                    <TableHead>Bestellnummer</TableHead>
                    <TableHead>Lieferant</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="min-w-[180px]">Match-Score</TableHead>
                    <TableHead className="text-right">Bestellung</TableHead>
                    <TableHead className="text-right">Lieferschein</TableHead>
                    <TableHead className="text-right">Rechnung</TableHead>
                    <TableHead className="text-center">Diff</TableHead>
                    <TableHead>Datum</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {paddingTop > 0 && (
                    <tr>
                      <td style={{ height: paddingTop }} colSpan={9} />
                    </tr>
                  )}
                  {virtualRows.map((virtualRow) => {
                    const match = matches[virtualRow.index];
                    const statusCfg = STATUS_CONFIG[match.match_status];
                    const hasDiff = hasAmountDeviation(match);

                    return (
                      <TableRow
                        key={match.id}
                        data-index={virtualRow.index}
                        className="cursor-pointer hover:bg-muted/50"
                        onClick={() => onSelectMatch(match.id)}
                        style={{ height: 48 }}
                      >
                        <TableCell className="font-medium">
                          {match.order_number || '-'}
                        </TableCell>
                        <TableCell>{match.vendor_name || '-'}</TableCell>
                        <TableCell>
                          <Badge
                            variant="outline"
                            className={cn('text-xs', statusCfg.className)}
                          >
                            {statusCfg.label}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <MatchScoreBar score={match.match_score} compact />
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {formatEUR(match.po_amount)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {formatEUR(match.dn_amount)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {formatEUR(match.invoice_amount)}
                        </TableCell>
                        <TableCell className="text-center">
                          {hasDiff ? (
                            <ArrowRightLeft className="h-4 w-4 text-red-500 mx-auto" />
                          ) : match.document_count >= 2 ? (
                            <CheckCircle2 className="h-4 w-4 text-green-500 mx-auto" />
                          ) : (
                            <span className="text-muted-foreground text-xs">-</span>
                          )}
                        </TableCell>
                        <TableCell className="tabular-nums">
                          {formatDate(match.created_at)}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                  {paddingBottom > 0 && (
                    <tr>
                      <td style={{ height: paddingBottom }} colSpan={9} />
                    </tr>
                  )}
                </TableBody>
              </Table>
            </div>

            {/* Paginierung */}
            <div className="flex items-center justify-between mt-4">
              <p className="text-sm text-muted-foreground">
                {total} Ergebnis{total !== 1 ? 'se' : ''} gesamt
                {isFetching && !isLoading && (
                  <Loader2 className="inline ml-2 h-3 w-3 animate-spin" />
                )}
              </p>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <span className="text-sm tabular-nums">
                  Seite {page + 1} von {totalPages}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setPage((p) => Math.min(totalPages - 1, p + 1))
                  }
                  disabled={page >= totalPages - 1}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ==================== Abgleich-Tab (Detail) ====================

function MatchDetailTab({
  matchId,
  onBack,
}: {
  matchId: string;
  onBack: () => void;
}) {
  const { data: match, isLoading } = usePOMatch(matchId);
  const approve = useApprovePOMatch();
  const evaluate = useEvaluatePOMatch();
  const [approveDialogOpen, setApproveDialogOpen] = useState(false);

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
          Zur\u00fcck zur \u00dcbersicht
        </Button>
      </div>
    );
  }

  const statusCfg = STATUS_CONFIG[match.match_status];
  const discrepancies = match.discrepancies ?? [];
  const unresolvedCount = discrepancies.filter((d) => !d.resolved).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={onBack}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Zur\u00fcck
          </Button>
          <div>
            <h2 className="text-2xl font-bold tracking-tight">
              {match.order_number
                ? `Bestellung ${match.order_number}`
                : `Match ${match.id.slice(0, 8)}...`}
            </h2>
            <p className="text-muted-foreground mt-1">
              {match.vendor_name || 'Unbekannter Lieferant'}
              {match.order_date && ` \u2013 ${formatDate(match.order_date)}`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <Badge
            variant="outline"
            className={cn('text-sm px-3 py-1', statusCfg.className)}
          >
            {statusCfg.label}
          </Badge>
          <div className="w-48">
            <p className="text-xs text-muted-foreground mb-1">Match-Score</p>
            <MatchScoreBar score={match.match_score} />
          </div>
        </div>
      </div>

      {/* 3-Spalten Vergleich mit Diff-Highlighting */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <DocumentColumn
          icon={<FileText className="h-5 w-5 text-blue-600" />}
          title="Bestellung"
          subtitle="Purchase Order"
          documentId={match.purchase_order_id}
          amount={match.po_amount}
          referenceAmount={match.po_amount}
          allAmounts={[match.po_amount, match.dn_amount, match.invoice_amount]}
          borderColor="border-t-blue-500"
        />
        <DocumentColumn
          icon={<Truck className="h-5 w-5 text-orange-600" />}
          title="Lieferschein"
          subtitle="Delivery Note"
          documentId={match.delivery_note_id}
          amount={match.dn_amount}
          referenceAmount={match.po_amount}
          allAmounts={[match.po_amount, match.dn_amount, match.invoice_amount]}
          borderColor="border-t-orange-500"
        />
        <DocumentColumn
          icon={<Receipt className="h-5 w-5 text-green-600" />}
          title="Rechnung"
          subtitle="Invoice"
          documentId={match.invoice_id}
          amount={match.invoice_amount}
          referenceAmount={match.po_amount}
          allAmounts={[match.po_amount, match.dn_amount, match.invoice_amount]}
          borderColor="border-t-green-500"
        />
      </div>

      {/* Match-Details */}
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
              <p className="text-muted-foreground">Vollst\u00e4ndig</p>
              <p className="font-medium">{match.is_complete ? 'Ja' : 'Nein'}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Auto-Match</p>
              <p className="font-medium">
                {match.auto_matched ? 'Ja' : 'Manuell'}
              </p>
            </div>
            <div>
              <p className="text-muted-foreground">Toleranz (Betrag / Menge)</p>
              <p className="font-medium tabular-nums">
                {match.amount_tolerance_percent}% / {match.quantity_tolerance_percent}%
              </p>
            </div>
            {match.approved_at && (
              <>
                <div>
                  <p className="text-muted-foreground">Freigegeben am</p>
                  <p className="font-medium">{formatDateTime(match.approved_at)}</p>
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

      {/* Abweichungen als Karten */}
      <div>
        <div className="flex items-center gap-2 mb-4">
          <AlertTriangle className="h-5 w-5" />
          <h3 className="text-lg font-semibold">
            Abweichungen ({discrepancies.length})
          </h3>
          {unresolvedCount > 0 && (
            <Badge variant="outline" className="bg-yellow-100 text-yellow-800 border-yellow-200 text-xs">
              {unresolvedCount} offen
            </Badge>
          )}
        </div>

        {discrepancies.length === 0 ? (
          <Card>
            <CardContent className="py-8">
              <div className="flex flex-col items-center text-muted-foreground">
                <CheckCircle2 className="h-10 w-10 mb-3 text-green-500" />
                <p className="text-sm font-medium">
                  Keine Abweichungen erkannt
                </p>
                <p className="text-xs mt-1">
                  Alle Werte stimmen innerhalb der Toleranz \u00fcberein.
                </p>
              </div>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {discrepancies.map((d) => (
              <DiscrepancyCard key={d.id} discrepancy={d} />
            ))}
          </div>
        )}
      </div>

      {/* Aktionen */}
      <div className="flex items-center gap-3 pt-2">
        <Button
          variant="outline"
          onClick={() => evaluate.mutate(matchId)}
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
                M\u00f6chten Sie diesen Match wirklich freigeben?
                {unresolvedCount > 0 && (
                  <span className="block mt-2 text-yellow-600 font-medium">
                    Achtung: Es gibt noch {unresolvedCount} ungel\u00f6ste
                    Abweichung{unresolvedCount !== 1 ? 'en' : ''}.
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
                onClick={() => {
                  approve.mutate(
                    { matchId },
                    { onSuccess: () => setApproveDialogOpen(false) }
                  );
                }}
                disabled={approve.isPending}
              >
                {approve.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="mr-2 h-4 w-4" />
                )}
                Freigabe best\u00e4tigen
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}

// ==================== Dokument-Spalte ====================

function DocumentColumn({
  icon,
  title,
  subtitle,
  documentId,
  amount,
  referenceAmount,
  allAmounts,
  borderColor,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  documentId: string | null;
  amount: number | null;
  referenceAmount: number | null;
  allAmounts: (number | null)[];
  borderColor: string;
}) {
  const nonNullAmounts = allAmounts.filter((a): a is number => a !== null);
  const hasDeviation =
    amount !== null &&
    nonNullAmounts.length >= 2 &&
    !nonNullAmounts.every((a) => a === nonNullAmounts[0]);

  const deviationFromRef =
    amount !== null && referenceAmount !== null && referenceAmount !== 0
      ? ((amount - referenceAmount) / referenceAmount) * 100
      : null;

  const showDeviation = deviationFromRef !== null && Math.abs(deviationFromRef) > 0.01;

  return (
    <Card className={cn('border-t-4', borderColor)}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          {icon}
          {title}
        </CardTitle>
        <CardDescription>{subtitle}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div>
          <p className="text-xs text-muted-foreground">Dokument-ID</p>
          <p className="text-sm font-mono">
            {documentId ? documentId.slice(0, 8) + '...' : 'Nicht verkn\u00fcpft'}
          </p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Betrag</p>
          <p
            className={cn(
              'text-lg font-semibold tabular-nums',
              hasDeviation && 'text-red-600'
            )}
          >
            {formatEUR(amount)}
          </p>
          {showDeviation && (
            <p
              className={cn(
                'text-xs tabular-nums mt-0.5',
                deviationFromRef > 0 ? 'text-red-500' : 'text-green-600'
              )}
            >
              {deviationFromRef > 0 ? '+' : ''}
              {deviationFromRef.toFixed(1)}% zur Bestellung
            </p>
          )}
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Status</p>
          <p className="text-sm">
            {documentId ? (
              <span className="text-green-600 font-medium">Verkn\u00fcpft</span>
            ) : (
              <span className="text-muted-foreground">Ausstehend</span>
            )}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

// ==================== Hauptkomponente ====================

export function ThreeWayMatchView({
  activeTab,
  selectedMatchId,
  onTabChange,
  onSelectMatch,
  onBack,
}: ThreeWayMatchViewProps) {
  // Wenn ein Match ausgewaehlt ist und wir im Abgleich-Tab sind
  if (activeTab === 'abgleich' && selectedMatchId) {
    return (
      <MatchDetailTab
        matchId={selectedMatchId}
        onBack={onBack}
      />
    );
  }

  const resolvedTab =
    activeTab === 'statistiken'
      ? 'statistiken'
      : activeTab === 'abgleich'
        ? 'abgleich'
        : '\u00fcbersicht';

  return (
    <Tabs value={resolvedTab} onValueChange={onTabChange}>
      <TabsList>
        <TabsTrigger value="\u00fcbersicht">\u00dcbersicht</TabsTrigger>
        <TabsTrigger value="abgleich" disabled={!selectedMatchId}>
          Abgleich
        </TabsTrigger>
        <TabsTrigger value="statistiken">Statistiken</TabsTrigger>
      </TabsList>

      <TabsContent value="\u00fcbersicht" className="mt-6">
        <MatchOverviewTab
          onSelectMatch={(id) => {
            onSelectMatch(id);
            onTabChange('abgleich');
          }}
        />
      </TabsContent>

      <TabsContent value="abgleich" className="mt-6">
        {selectedMatchId ? (
          <MatchDetailTab matchId={selectedMatchId} onBack={onBack} />
        ) : (
          <Card>
            <CardContent className="py-12">
              <div className="flex flex-col items-center text-muted-foreground">
                <FileSearch className="h-12 w-12 mb-4" />
                <p className="text-lg font-medium">
                  Kein Match ausgew\u00e4hlt
                </p>
                <p className="text-sm mt-1">
                  W\u00e4hlen Sie einen Match aus der \u00dcbersicht, um den
                  detaillierten Abgleich zu sehen.
                </p>
              </div>
            </CardContent>
          </Card>
        )}
      </TabsContent>

      <TabsContent value="statistiken" className="mt-6">
        <POMatchStats />
      </TabsContent>
    </Tabs>
  );
}
