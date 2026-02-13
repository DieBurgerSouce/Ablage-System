import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { RefreshCw } from 'lucide-react';
import type { InboxStatus, InboxCategory, InboxSortBy } from '../types/smart-inbox-types';

interface InboxFiltersProps {
  statusFilter: InboxStatus | 'all';
  categoryFilter: InboxCategory | 'all';
  sortBy: InboxSortBy;
  availableCategories: InboxCategory[];
  onStatusChange: (status: InboxStatus | 'all') => void;
  onCategoryChange: (category: InboxCategory | 'all') => void;
  onSortChange: (sort: InboxSortBy) => void;
  onRefresh: () => void;
  isRefreshing: boolean;
}

const CATEGORY_LABELS: Record<string, string> = {
  invoice_overdue: 'Rechnung überfällig',
  invoice_due_soon: 'Rechnung bald fällig',
  invoice_pending: 'Rechnung ausstehend',
  skonto_expiring: 'Skonto läuft ab',
  document_needs_review: 'Prüfung nötig',
  entity_risk_high: 'Hohes Risiko',
  chain_incomplete: 'Kette unvollständig',
  shipment_delayed: 'Sendung verzögert',
  payment_received: 'Zahlung eingegangen',
  alert_critical: 'Kritisch',
  alert_warning: 'Warnung',
  alert_info: 'Information',
};

export function InboxFilters({
  statusFilter,
  categoryFilter,
  sortBy,
  availableCategories,
  onStatusChange,
  onCategoryChange,
  onSortChange,
  onRefresh,
  isRefreshing,
}: InboxFiltersProps) {
  return (
    <div className="flex flex-col sm:flex-row gap-3">
      <Select
        value={statusFilter}
        onValueChange={(v) => onStatusChange(v as InboxStatus | 'all')}
      >
        <SelectTrigger className="w-full sm:w-[180px]">
          <SelectValue placeholder="Status" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">Alle Status</SelectItem>
          <SelectItem value="pending">Ausstehend</SelectItem>
          <SelectItem value="in_progress">In Bearbeitung</SelectItem>
          <SelectItem value="completed">Erledigt</SelectItem>
          <SelectItem value="dismissed">Verworfen</SelectItem>
        </SelectContent>
      </Select>

      <Select
        value={categoryFilter}
        onValueChange={(v) => onCategoryChange(v as InboxCategory | 'all')}
      >
        <SelectTrigger className="w-full sm:w-[200px]">
          <SelectValue placeholder="Kategorie" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">Alle Kategorien</SelectItem>
          {availableCategories.map((cat) => (
            <SelectItem key={cat} value={cat}>
              {CATEGORY_LABELS[cat] ?? cat}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={sortBy}
        onValueChange={(v) => onSortChange(v as InboxSortBy)}
      >
        <SelectTrigger className="w-full sm:w-[180px]">
          <SelectValue placeholder="Sortierung" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="mlPriority">ML-Priorität</SelectItem>
          <SelectItem value="deadline">Fälligkeit</SelectItem>
          <SelectItem value="createdAt">Neueste zuerst</SelectItem>
        </SelectContent>
      </Select>

      <Button
        variant="outline"
        size="icon"
        onClick={onRefresh}
        disabled={isRefreshing}
        title="Aktualisieren"
      >
        <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
      </Button>
    </div>
  );
}
