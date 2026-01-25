/**
 * Payment Suggestions Table
 *
 * Tabelle mit Zahlungsvorschlaegen und Aktionen.
 */

import { useState } from 'react';
import {
  Banknote,
  Clock,
  AlertTriangle,
  CheckCircle,
  ChevronUp,
  ChevronDown,
  Loader2,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Checkbox } from '@/components/ui/checkbox';
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
import { toast } from 'sonner';
import {
  usePaymentSuggestions,
  useCreateBatch,
  type PaymentSuggestion,
  type PaymentStrategy,
  type PaymentPriority,
} from '../hooks/usePaymentAutomation';

const PRIORITY_CONFIG: Record<PaymentPriority, { label: string; color: string; icon: typeof AlertTriangle }> = {
  critical: { label: 'Kritisch', color: 'text-red-500', icon: AlertTriangle },
  high: { label: 'Hoch', color: 'text-orange-500', icon: ChevronUp },
  normal: { label: 'Normal', color: 'text-blue-500', icon: Clock },
  low: { label: 'Niedrig', color: 'text-gray-500', icon: ChevronDown },
};

const REASON_LABELS: Record<string, string> = {
  skonto_expiring: 'Skonto laeuft ab',
  due_date_near: 'Faelligkeit naht',
  overdue: 'Ueberfaellig',
  approved_invoice: 'Genehmigt',
  recurring_payment: 'Wiederkehrend',
  manual_request: 'Manuell',
};

function PriorityBadge({ priority }: { priority: PaymentPriority }) {
  const config = PRIORITY_CONFIG[priority];
  const Icon = config.icon;

  return (
    <Badge variant="outline" className={`${config.color} gap-1`}>
      <Icon className="h-3 w-3" />
      {config.label}
    </Badge>
  );
}

function formatCurrency(amount: number): string {
  return amount.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' });
}

function formatDate(dateString: string | null): string {
  if (!dateString) return '-';
  return new Date(dateString).toLocaleDateString('de-DE');
}

interface SuggestionRowProps {
  suggestion: PaymentSuggestion;
  selected: boolean;
  onToggle: (id: string) => void;
}

function SuggestionRow({ suggestion, selected, onToggle }: SuggestionRowProps) {
  return (
    <TableRow className={selected ? 'bg-muted/50' : ''}>
      <TableCell>
        <Checkbox
          checked={selected}
          onCheckedChange={() => onToggle(suggestion.id)}
        />
      </TableCell>
      <TableCell>
        <div>
          <p className="font-medium">{suggestion.invoice_number || 'Ohne Nr.'}</p>
          <p className="text-sm text-muted-foreground">{suggestion.entity_name}</p>
        </div>
      </TableCell>
      <TableCell>
        <PriorityBadge priority={suggestion.priority} />
        <p className="text-xs text-muted-foreground mt-1">
          {REASON_LABELS[suggestion.reason] || suggestion.reason}
        </p>
      </TableCell>
      <TableCell className="text-right">
        <div>
          <p className="font-medium">{formatCurrency(suggestion.payment_amount)}</p>
          {suggestion.use_skonto && suggestion.skonto_savings > 0 && (
            <p className="text-xs text-green-500">
              -{formatCurrency(suggestion.skonto_savings)} Skonto
            </p>
          )}
        </div>
      </TableCell>
      <TableCell>
        {suggestion.skonto_deadline && (
          <div className={suggestion.days_until_skonto !== null && suggestion.days_until_skonto <= 3 ? 'text-amber-500' : ''}>
            <p className="text-sm">{formatDate(suggestion.skonto_deadline)}</p>
            {suggestion.days_until_skonto !== null && (
              <p className="text-xs text-muted-foreground">
                {suggestion.days_until_skonto <= 0 ? 'Heute!' : `${suggestion.days_until_skonto} Tage`}
              </p>
            )}
          </div>
        )}
      </TableCell>
      <TableCell>
        <div className={suggestion.days_until_due !== null && suggestion.days_until_due < 0 ? 'text-red-500' : ''}>
          <p className="text-sm">{formatDate(suggestion.due_date)}</p>
          {suggestion.days_until_due !== null && (
            <p className="text-xs text-muted-foreground">
              {suggestion.days_until_due < 0
                ? `${Math.abs(suggestion.days_until_due)} Tage ueberfaellig`
                : suggestion.days_until_due === 0
                  ? 'Heute faellig'
                  : `${suggestion.days_until_due} Tage`}
            </p>
          )}
        </div>
      </TableCell>
      <TableCell>
        <p className="text-sm">{formatDate(suggestion.suggested_payment_date)}</p>
      </TableCell>
    </TableRow>
  );
}

export function PaymentSuggestionsTable() {
  const [strategy, setStrategy] = useState<PaymentStrategy>('skonto_optimized');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const { data: suggestions, isLoading } = usePaymentSuggestions(strategy);
  const createBatchMutation = useCreateBatch();

  const handleToggle = (id: string) => {
    const newSelected = new Set(selectedIds);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelectedIds(newSelected);
  };

  const handleSelectAll = () => {
    if (!suggestions) return;
    if (selectedIds.size === suggestions.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(suggestions.map((s) => s.id)));
    }
  };

  const handleCreateBatch = async () => {
    if (selectedIds.size === 0) {
      toast.error('Bitte waehlen Sie mindestens einen Vorschlag aus');
      return;
    }

    const selectedSuggestions = suggestions?.filter((s) => selectedIds.has(s.id)) || [];
    const invoiceIds = selectedSuggestions.map((s) => s.invoice_id);

    try {
      await createBatchMutation.mutateAsync({ invoiceIds });
      toast.success(`Batch mit ${invoiceIds.length} Zahlungen erstellt`);
      setSelectedIds(new Set());
    } catch {
      toast.error('Fehler beim Erstellen des Batches');
    }
  };

  const totalSelected = suggestions?.filter((s) => selectedIds.has(s.id)) || [];
  const totalAmount = totalSelected.reduce((sum, s) => sum + s.payment_amount, 0);
  const totalSavings = totalSelected.reduce((sum, s) => sum + (s.use_skonto ? s.skonto_savings : 0), 0);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Banknote className="h-5 w-5" />
            Zahlungsvorschlaege
          </CardTitle>
          <CardDescription>
            Offene Rechnungen priorisiert nach Strategie
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          <Select value={strategy} onValueChange={(v) => setStrategy(v as PaymentStrategy)}>
            <SelectTrigger className="w-[200px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="skonto_optimized">Skonto-optimiert</SelectItem>
              <SelectItem value="cashflow_optimized">Cashflow-optimiert</SelectItem>
              <SelectItem value="deadline_based">Nach Faelligkeit</SelectItem>
              <SelectItem value="immediate">Sofortzahlung</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        ) : suggestions && suggestions.length > 0 ? (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12">
                    <Checkbox
                      checked={selectedIds.size === suggestions.length && suggestions.length > 0}
                      onCheckedChange={handleSelectAll}
                    />
                  </TableHead>
                  <TableHead>Rechnung</TableHead>
                  <TableHead>Prioritaet</TableHead>
                  <TableHead className="text-right">Betrag</TableHead>
                  <TableHead>Skonto bis</TableHead>
                  <TableHead>Faellig</TableHead>
                  <TableHead>Zahlung am</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {suggestions.map((suggestion) => (
                  <SuggestionRow
                    key={suggestion.id}
                    suggestion={suggestion}
                    selected={selectedIds.has(suggestion.id)}
                    onToggle={handleToggle}
                  />
                ))}
              </TableBody>
            </Table>

            {/* Selection Summary and Actions */}
            {selectedIds.size > 0 && (
              <div className="flex items-center justify-between mt-4 p-4 bg-muted rounded-lg">
                <div>
                  <p className="font-medium">{selectedIds.size} Zahlungen ausgewaehlt</p>
                  <div className="flex items-center gap-4 text-sm text-muted-foreground">
                    <span>Gesamt: {formatCurrency(totalAmount)}</span>
                    {totalSavings > 0 && (
                      <span className="text-green-500">
                        Skonto-Ersparnis: {formatCurrency(totalSavings)}
                      </span>
                    )}
                  </div>
                </div>
                <Button onClick={handleCreateBatch} disabled={createBatchMutation.isPending}>
                  {createBatchMutation.isPending ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <CheckCircle className="h-4 w-4 mr-2" />
                  )}
                  Batch erstellen
                </Button>
              </div>
            )}
          </>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            <Banknote className="h-12 w-12 mx-auto mb-4 opacity-20" />
            <p>Keine Zahlungsvorschlaege verfuegbar</p>
            <p className="text-sm mt-1">
              Alle offenen Rechnungen sind bereits beglichen oder haben keine Faelligkeit
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
