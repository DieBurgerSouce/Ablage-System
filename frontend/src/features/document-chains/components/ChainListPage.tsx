/**
 * ChainListPage - Auftragsketten-Uebersichtsseite
 *
 * Listet alle Auftragsketten mit Filtermoeglichkeiten.
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Link2,
  Search,
  Plus,
  Loader2,
  AlertTriangle,
  CheckCircle,
  Clock,
  RefreshCw,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { ChainCard, ChainCardCompact } from './ChainCard';
import { CreateChainDialog } from './CreateChainDialog';
import {
  type ChainStatus,
  type ChainFilter,
  CHAIN_UI_LABELS,
} from '../types/chain-types';
import { useChains } from '../hooks/use-chain-queries';

interface ChainListPageProps {
  onChainClick?: (chainId: string) => void;
  className?: string;
}

export function ChainListPage({ onChainClick, className }: ChainListPageProps) {
  const [filter, setFilter] = useState<Partial<ChainFilter>>({
    page: 1,
    perPage: 20,
  });
  const [statusFilter, setStatusFilter] = useState<ChainStatus | 'all'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [viewMode, setViewMode] = useState<'cards' | 'list'>('cards');
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  const chainsQuery = useChains({
    ...filter,
    status: statusFilter === 'all' ? undefined : statusFilter,
  });

  const chains = chainsQuery.data ?? [];

  // Filter by search query (client-side)
  const filteredChains = chains.filter((chain) => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      chain.name?.toLowerCase().includes(query) ||
      chain.chainId.toLowerCase().includes(query) ||
      chain.documents.some(
        (doc) =>
          doc.filename.toLowerCase().includes(query) ||
          doc.referenceNumber?.toLowerCase().includes(query) ||
          doc.businessEntityName?.toLowerCase().includes(query)
      )
    );
  });

  // Statistics
  const stats = {
    total: chains.length,
    complete: chains.filter((c) => c.status === 'complete').length,
    inProgress: chains.filter((c) => c.status === 'in_progress').length,
    hasIssues: chains.filter((c) => c.status === 'has_issues').length,
  };

  const handleStatusChange = (value: string) => {
    setStatusFilter(value as ChainStatus | 'all');
  };

  return (
    <div className={cn('space-y-6', className)}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Link2 className="w-6 h-6" />
            {CHAIN_UI_LABELS.pageTitle}
          </h1>
          <p className="text-muted-foreground">{CHAIN_UI_LABELS.pageDescription}</p>
        </div>
        <Button onClick={() => setIsCreateOpen(true)}>
          <Plus className="w-4 h-4 mr-2" />
          {CHAIN_UI_LABELS.actionCreateChain}
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard
          label="Gesamt"
          value={stats.total}
          icon={Link2}
          className="bg-slate-50"
        />
        <StatCard
          label={CHAIN_UI_LABELS.statusComplete}
          value={stats.complete}
          icon={CheckCircle}
          className="bg-green-50 text-green-700"
        />
        <StatCard
          label={CHAIN_UI_LABELS.statusInProgress}
          value={stats.inProgress}
          icon={Clock}
          className="bg-blue-50 text-blue-700"
        />
        <StatCard
          label={CHAIN_UI_LABELS.statusHasIssues}
          value={stats.hasIssues}
          icon={AlertTriangle}
          className="bg-yellow-50 text-yellow-700"
        />
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-4">
          <div className="flex items-center gap-4">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Suche nach Name, Referenz, Firma..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9"
              />
            </div>
            <Select value={statusFilter} onValueChange={handleStatusChange}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Status filtern" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Alle Status</SelectItem>
                <SelectItem value="complete">{CHAIN_UI_LABELS.statusComplete}</SelectItem>
                <SelectItem value="in_progress">{CHAIN_UI_LABELS.statusInProgress}</SelectItem>
                <SelectItem value="has_issues">{CHAIN_UI_LABELS.statusHasIssues}</SelectItem>
              </SelectContent>
            </Select>
            <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as 'cards' | 'list')}>
              <TabsList>
                <TabsTrigger value="cards">Karten</TabsTrigger>
                <TabsTrigger value="list">Liste</TabsTrigger>
              </TabsList>
            </Tabs>
            <Button
              variant="outline"
              size="icon"
              onClick={() => chainsQuery.refetch()}
              disabled={chainsQuery.isFetching}
            >
              <RefreshCw
                className={cn('w-4 h-4', chainsQuery.isFetching && 'animate-spin')}
              />
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Loading */}
      {chainsQuery.isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Empty state */}
      {!chainsQuery.isLoading && filteredChains.length === 0 && (
        <Card>
          <CardContent className="py-12">
            <div className="text-center text-muted-foreground">
              <Link2 className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium mb-1">
                {searchQuery ? 'Keine Ergebnisse' : CHAIN_UI_LABELS.emptyNoChains}
              </h3>
              <p className="text-sm">
                {searchQuery
                  ? 'Versuchen Sie eine andere Suchanfrage.'
                  : 'Erstellen Sie Ihre erste Auftragskette, um Dokumente zu verknuepfen.'}
              </p>
              {!searchQuery && (
                <Button className="mt-4" onClick={() => setIsCreateOpen(true)}>
                  <Plus className="w-4 h-4 mr-2" />
                  {CHAIN_UI_LABELS.actionCreateChain}
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Chain List */}
      {!chainsQuery.isLoading && filteredChains.length > 0 && (
        <>
          {viewMode === 'cards' ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredChains.map((chain) => (
                <ChainCard
                  key={chain.chainId}
                  chain={chain}
                  onClick={() => onChainClick?.(chain.chainId)}
                />
              ))}
            </div>
          ) : (
            <Card>
              <CardContent className="p-4 space-y-2">
                {filteredChains.map((chain) => (
                  <ChainCardCompact
                    key={chain.chainId}
                    chain={chain}
                    onClick={() => onChainClick?.(chain.chainId)}
                  />
                ))}
              </CardContent>
            </Card>
          )}
        </>
      )}

      {/* Create Dialog */}
      <CreateChainDialog
        open={isCreateOpen}
        onOpenChange={setIsCreateOpen}
        onSuccess={(chainId) => onChainClick?.(chainId)}
      />
    </div>
  );
}

// Stat Card Component
function StatCard({
  label,
  value,
  icon: Icon,
  className,
}: {
  label: string;
  value: number;
  icon: typeof Link2;
  className?: string;
}) {
  return (
    <Card className={cn('', className)}>
      <CardContent className="pt-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-2xl font-bold">{value}</div>
            <div className="text-sm text-muted-foreground">{label}</div>
          </div>
          <Icon className="w-8 h-8 opacity-50" />
        </div>
      </CardContent>
    </Card>
  );
}
