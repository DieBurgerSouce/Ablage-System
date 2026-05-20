// Hint List - Filterable list of hints with pagination

import { useState } from 'react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { AlertCircle, Filter, RefreshCw } from 'lucide-react';
import { HintCard } from './HintCard';
import { useHintsQuery } from '../hooks/use-proactive-assistant-queries';
import {
  UI_LABELS,
  type HintCategory,
  type HintPriority,
  type HintStatus,
} from '../types/proactive-assistant-types';

const ITEMS_PER_PAGE = 10;

export function HintList() {
  const [category, setCategory] = useState<HintCategory | 'all'>('all');
  const [priority, setPriority] = useState<HintPriority | 'all'>('all');
  const [status, setStatus] = useState<HintStatus | 'all'>('all');
  const [page, setPage] = useState(0);

  const { data, isLoading, error, refetch } = useHintsQuery({
    category: category === 'all' ? undefined : category,
    priority: priority === 'all' ? undefined : priority,
    status: status === 'all' ? undefined : status,
    limit: ITEMS_PER_PAGE,
    offset: page * ITEMS_PER_PAGE,
  });

  const handleCategoryChange = (value: string) => {
    setCategory(value as HintCategory | 'all');
    setPage(0);
  };

  const handlePriorityChange = (value: string) => {
    setPriority(value as HintPriority | 'all');
    setPage(0);
  };

  const handleStatusChange = (value: string) => {
    setStatus(value as HintStatus | 'all');
    setPage(0);
  };

  const totalPages = data ? Math.ceil(data.totalCount / ITEMS_PER_PAGE) : 0;

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4 p-4 bg-muted/50 rounded-lg">
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium">Filter:</span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Select value={category} onValueChange={handleCategoryChange}>
            <SelectTrigger className="w-40">
              <SelectValue placeholder={UI_LABELS.filters.category} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{UI_LABELS.filters.all}</SelectItem>
              <SelectItem value="fristen">
                {UI_LABELS.categories.fristen}
              </SelectItem>
              <SelectItem value="anomalien">
                {UI_LABELS.categories.anomalien}
              </SelectItem>
              <SelectItem value="optimierung">
                {UI_LABELS.categories.optimierung}
              </SelectItem>
            </SelectContent>
          </Select>

          <Select value={priority} onValueChange={handlePriorityChange}>
            <SelectTrigger className="w-40">
              <SelectValue placeholder={UI_LABELS.filters.priority} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{UI_LABELS.filters.all}</SelectItem>
              <SelectItem value="low">
                {UI_LABELS.priorities.low}
              </SelectItem>
              <SelectItem value="medium">
                {UI_LABELS.priorities.medium}
              </SelectItem>
              <SelectItem value="high">
                {UI_LABELS.priorities.high}
              </SelectItem>
              <SelectItem value="critical">
                {UI_LABELS.priorities.critical}
              </SelectItem>
            </SelectContent>
          </Select>

          <Select value={status} onValueChange={handleStatusChange}>
            <SelectTrigger className="w-40">
              <SelectValue placeholder={UI_LABELS.filters.status} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{UI_LABELS.filters.all}</SelectItem>
              <SelectItem value="new">{UI_LABELS.statuses.new}</SelectItem>
              <SelectItem value="seen">{UI_LABELS.statuses.seen}</SelectItem>
              <SelectItem value="confirmed">
                {UI_LABELS.statuses.confirmed}
              </SelectItem>
              <SelectItem value="dismissed">
                {UI_LABELS.statuses.dismissed}
              </SelectItem>
              <SelectItem value="acted">{UI_LABELS.statuses.acted}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={() => refetch()}
          disabled={isLoading}
        >
          <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      {/* Error State */}
      {error && (
        <div className="flex items-center gap-2 p-4 bg-destructive/10 border border-destructive rounded-lg text-destructive">
          <AlertCircle className="h-5 w-5" />
          <div className="flex-1">
            <p className="text-sm font-medium">
              {UI_LABELS.messages.errorLoadingHints}
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            {UI_LABELS.actions.retry}
          </Button>
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-48" />
          ))}
        </div>
      )}

      {/* Hints List */}
      {!isLoading && data && (
        <>
          {data.hints.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-muted-foreground">
                {UI_LABELS.messages.noHints}
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {data.hints.map((hint) => (
                <HintCard key={hint.hintId} hint={hint} />
              ))}
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between pt-4">
              <p className="text-sm text-muted-foreground">
                Seite {page + 1} von {totalPages} ({data.totalCount} Hinweise
                gesamt)
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                >
                  Zurück
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                >
                  Weiter
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
