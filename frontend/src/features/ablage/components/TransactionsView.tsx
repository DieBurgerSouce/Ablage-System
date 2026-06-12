/**
 * TransactionsView - Vorgänge-Übersicht
 *
 * Zeigt alle Vorgänge eines Kunden/Lieferanten als Liste.
 * Jeder Vorgang wird mit horizontaler Timeline dargestellt.
 *
 * Features:
 * - Suche nach Vorgangsnummer oder Name
 * - Filter nach Status
 * - Sortierung nach Datum, Betrag, Status
 * - Pagination
 */

import { useState, useCallback, useMemo, useEffect } from 'react';
import { useParams, useNavigate } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { logger } from '@/lib/logger';
import {
  Search,
  Filter,
  SortAsc,
  SortDesc,
  Plus,
  AlertCircle,
  FileStack,
  ArrowLeft,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Breadcrumbs } from '@/components/ui/breadcrumb';
import { DocumentListSkeleton } from '@/components/ui/skeletons/DocumentListSkeleton';
import { TransactionListItem } from './TransactionTimeline';
import { transactionsService } from '@/lib/api/services/transactions';
import type {
  Transaction,
  TransactionStatus,
  TransactionFilter,
  TransactionStep,
} from '../types';
import { DEFAULT_TRANSACTION_FILTER } from '../types';

// ==================== Types ====================

interface TransactionsViewProps {
  entityType: 'customer' | 'supplier';
}

type SortField = 'createdAt' | 'lastActivityAt' | 'totalAmount' | 'transactionNumber';
type SortOrder = 'asc' | 'desc';

// ==================== Helper Functions ====================

const STATUS_LABELS: Record<TransactionStatus, string> = {
  draft: 'Entwurf',
  pending: 'In Bearbeitung',
  completed: 'Abgeschlossen',
  cancelled: 'Abgebrochen',
};

// ==================== Sub-Components ====================

function TransactionsHeader({
  totalCount,
}: {
  totalCount: number;
}) {
  return (
    <div className="space-y-4">
      {/* Breadcrumb - uses automatic route-based breadcrumbs */}
      <Breadcrumbs />

      {/* Title */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <FileStack className="w-8 h-8 text-blue-600" />
          <div>
            <h1 className="text-2xl font-bold">Vorgänge</h1>
            <p className="text-sm text-muted-foreground">
              {totalCount} Vorgang{totalCount !== 1 ? 'e' : ''} gefunden
            </p>
          </div>
        </div>

        <Button className="gap-2">
          <Plus className="w-4 h-4" />
          Neuer Vorgang
        </Button>
      </div>
    </div>
  );
}

function TransactionsFilterBar({
  search,
  onSearchChange,
  statusFilter,
  onStatusChange,
  sortField,
  onSortFieldChange,
  sortOrder,
  onSortOrderChange,
}: {
  search: string;
  onSearchChange: (value: string) => void;
  statusFilter: TransactionStatus | 'all';
  onStatusChange: (value: TransactionStatus | 'all') => void;
  sortField: SortField;
  onSortFieldChange: (value: SortField) => void;
  sortOrder: SortOrder;
  onSortOrderChange: (value: SortOrder) => void;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex flex-wrap items-center gap-4">
          {/* Search */}
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Suche nach Vorgangsnummer oder Name..."
              value={search}
              onChange={(e) => onSearchChange(e.target.value)}
              className="pl-10"
            />
          </div>

          {/* Status Filter */}
          <Select value={statusFilter} onValueChange={(v) => onStatusChange(v as TransactionStatus | 'all')}>
            <SelectTrigger className="w-[180px]">
              <Filter className="w-4 h-4 mr-2" />
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle Status</SelectItem>
              <SelectItem value="draft">Entwurf</SelectItem>
              <SelectItem value="pending">In Bearbeitung</SelectItem>
              <SelectItem value="completed">Abgeschlossen</SelectItem>
              <SelectItem value="cancelled">Abgebrochen</SelectItem>
            </SelectContent>
          </Select>

          {/* Sort Field */}
          <Select value={sortField} onValueChange={(v) => onSortFieldChange(v as SortField)}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Sortieren nach" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="lastActivityAt">Letzte Aktivität</SelectItem>
              <SelectItem value="createdAt">Erstellt am</SelectItem>
              <SelectItem value="totalAmount">Betrag</SelectItem>
              <SelectItem value="transactionNumber">Vorgangsnummer</SelectItem>
            </SelectContent>
          </Select>

          {/* Sort Order Toggle */}
          <Button
            variant="outline"
            size="icon"
            onClick={() => onSortOrderChange(sortOrder === 'asc' ? 'desc' : 'asc')}
          >
            {sortOrder === 'asc' ? (
              <SortAsc className="w-4 h-4" />
            ) : (
              <SortDesc className="w-4 h-4" />
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function TransactionsSummary({
  transactions,
}: {
  transactions: Transaction[];
}) {
  const stats = useMemo(() => {
    const byStatus = transactions.reduce(
      (acc, t) => {
        acc[t.status] = (acc[t.status] || 0) + 1;
        return acc;
      },
      {} as Record<TransactionStatus, number>
    );

    const totalAmount = transactions.reduce(
      (sum, t) => sum + (t.totalAmount || 0),
      0
    );

    const completedAmount = transactions
      .filter((t) => t.status === 'completed')
      .reduce((sum, t) => sum + (t.totalAmount || 0), 0);

    const pendingAmount = transactions
      .filter((t) => t.status === 'pending')
      .reduce((sum, t) => sum + (t.totalAmount || 0), 0);

    return {
      byStatus,
      totalAmount,
      completedAmount,
      pendingAmount,
    };
  }, [transactions]);

  const formatCurrency = (amount: number) =>
    new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
    }).format(amount);

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      <Card>
        <CardContent className="p-4">
          <p className="text-sm text-muted-foreground">Gesamt</p>
          <p className="text-2xl font-bold">{transactions.length}</p>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4">
          <p className="text-sm text-muted-foreground">In Bearbeitung</p>
          <p className="text-2xl font-bold text-blue-600">
            {stats.byStatus.pending || 0}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4">
          <p className="text-sm text-muted-foreground">Abgeschlossen</p>
          <p className="text-2xl font-bold text-green-600">
            {stats.byStatus.completed || 0}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4">
          <p className="text-sm text-muted-foreground">Offener Betrag</p>
          <p className="text-2xl font-bold">
            {formatCurrency(stats.pendingAmount)}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function TransactionsEmptyState({
  hasFilters,
}: {
  hasFilters: boolean;
}) {
  return (
    <Card>
      <CardContent className="py-12">
        <div className="text-center">
          <FileStack className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold mb-2">
            {hasFilters ? 'Keine Vorgänge gefunden' : 'Noch keine Vorgänge'}
          </h3>
          <p className="text-muted-foreground mb-4">
            {hasFilters
              ? 'Versuchen Sie andere Filterkriterien.'
              : 'Erstellen Sie Ihren ersten Vorgang, um Dokumente zu verknüpfen.'}
          </p>
          {!hasFilters && (
            <Button className="gap-2">
              <Plus className="w-4 h-4" />
              Ersten Vorgang erstellen
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ==================== Main Component ====================

export function TransactionsView({ entityType }: TransactionsViewProps) {
  const params = useParams({ strict: false });
  const navigate = useNavigate();
  const isCustomer = entityType === 'customer';

  // Extract route params
  const entityId = isCustomer ? params.customerId : params.supplierId;
  const folderId = params.folderId;

  // Filter state
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<TransactionStatus | 'all'>('all');
  const [sortField, setSortField] = useState<SortField>('lastActivityAt');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');
  const [page, setPage] = useState(1);

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  // Build filter
  const filter: TransactionFilter = useMemo(
    () => ({
      ...DEFAULT_TRANSACTION_FILTER,
      entityId,
      folderId,
      status: statusFilter !== 'all' ? [statusFilter] : undefined,
      search: debouncedSearch || undefined,
      page,
      pageSize: 20,
    }),
    [entityId, folderId, statusFilter, debouncedSearch, page]
  );

  // Fetch transactions
  const {
    data,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ['transactions', filter],
    queryFn: () => transactionsService.list(filter),
    enabled: !!entityId && !!folderId,
  });

  const transactions = data?.items || [];
  const totalCount = data?.total || 0;

  // Filter and sort - API handles primary filtering, client-side as backup
  const filteredTransactions = useMemo(() => {
    let result = [...transactions];

    // Client-side filtering (backup for additional refinement)
    if (debouncedSearch) {
      const searchLower = debouncedSearch.toLowerCase();
      result = result.filter(
        (t) =>
          t.transactionNumber.toLowerCase().includes(searchLower) ||
          t.name.toLowerCase().includes(searchLower)
      );
    }

    if (statusFilter !== 'all') {
      result = result.filter((t) => t.status === statusFilter);
    }

    // Sort client-side (API sorting may be limited)
    result.sort((a, b) => {
      let comparison = 0;
      switch (sortField) {
        case 'createdAt':
          comparison = new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime();
          break;
        case 'lastActivityAt':
          comparison = new Date(a.lastActivityAt).getTime() - new Date(b.lastActivityAt).getTime();
          break;
        case 'totalAmount':
          comparison = (a.totalAmount || 0) - (b.totalAmount || 0);
          break;
        case 'transactionNumber':
          comparison = a.transactionNumber.localeCompare(b.transactionNumber);
          break;
      }
      return sortOrder === 'asc' ? comparison : -comparison;
    });

    return result;
  }, [transactions, debouncedSearch, statusFilter, sortField, sortOrder]);

  const hasFilters = !!debouncedSearch || statusFilter !== 'all';

  // Handlers
  const handleTransactionClick = useCallback(
    (transaction: Transaction) => {
      // Navigiere zum ersten Dokument des Vorgangs (falls vorhanden)
      const firstDocumentStep = transaction.steps.find((step) => step.documentId);
      if (firstDocumentStep?.documentId) {
        logger.debug('Navigiere zu Vorgang-Dokument:', {
          transactionId: transaction.id,
          documentId: firstDocumentStep.documentId,
        });
        navigate({
          to: '/documents/$documentId',
          params: { documentId: firstDocumentStep.documentId },
        });
      } else {
        logger.debug('Vorgang hat keine Dokumente:', { transactionId: transaction.id });
      }
    },
    [navigate]
  );

  const handleStepClick = useCallback(
    (step: TransactionStep) => {
      if (step.documentId) {
        logger.debug('Navigiere zu Dokument:', { documentId: step.documentId });
        navigate({
          to: '/documents/$documentId',
          params: { documentId: step.documentId },
        });
      }
    },
    [navigate]
  );

  const handleBack = useCallback(() => {
    const basePath = isCustomer ? '/kunden' : '/lieferanten';
    navigate({ to: `${basePath}/${entityId}/${folderId}` as string });
  }, [isCustomer, entityId, folderId, navigate]);

  // Missing params
  if (!entityId || !folderId) {
    return (
      <div className="p-8">
        <Card>
          <CardContent className="py-8">
            <p className="text-center text-muted-foreground">
              Ungültige Parameter. Bitte wählen Sie einen Ordner aus.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="p-8 space-y-6">
      {/* Back Button */}
      <Button variant="ghost" className="gap-2 mb-4" onClick={handleBack}>
        <ArrowLeft className="w-4 h-4" />
        Zurück zu Kategorien
      </Button>

      {/* Header */}
      <TransactionsHeader
        totalCount={filteredTransactions.length}
      />

      {/* Summary Cards */}
      {!isLoading && transactions.length > 0 && (
        <TransactionsSummary transactions={transactions} />
      )}

      {/* Filter Bar */}
      <TransactionsFilterBar
        search={search}
        onSearchChange={setSearch}
        statusFilter={statusFilter}
        onStatusChange={setStatusFilter}
        sortField={sortField}
        onSortFieldChange={setSortField}
        sortOrder={sortOrder}
        onSortOrderChange={setSortOrder}
      />

      {/* Loading State */}
      {isLoading && (
        <Card>
          <CardContent className="py-4">
            <DocumentListSkeleton variant="shimmer" />
          </CardContent>
        </Card>
      )}

      {/* Error State */}
      {isError && (
        <Card>
          <CardContent className="py-8">
            <div className="flex flex-col items-center text-destructive">
              <AlertCircle className="w-8 h-8 mb-2" />
              <p>
                Fehler beim Laden der Vorgänge:{' '}
                {error instanceof Error ? error.message : 'Unbekannter Fehler'}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Empty State */}
      {!isLoading && !isError && filteredTransactions.length === 0 && (
        <TransactionsEmptyState hasFilters={hasFilters} />
      )}

      {/* Transaction List */}
      {!isLoading && !isError && filteredTransactions.length > 0 && (
        <div className="space-y-4">
          {filteredTransactions.map((transaction) => (
            <TransactionListItem
              key={transaction.id}
              transaction={transaction}
              onClick={() => handleTransactionClick(transaction)}
              onStepClick={handleStepClick}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default TransactionsView;
