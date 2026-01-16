/**
 * InvoiceActions - Aktionen-Dropdown für einzelne Rechnung
 *
 * Aktionen:
 * - Als bezahlt markieren
 * - Mahnstufe erhöhen
 * - Details anzeigen
 */

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  MoreHorizontal,
  CheckCircle,
  TrendingUp,
  Eye,
  XCircle,
} from 'lucide-react';
import type { InvoiceTrackingResponse } from '../types/invoice-types';
import { UI_LABELS } from '../types/invoice-types';

interface InvoiceActionsProps {
  invoice: InvoiceTrackingResponse;
  onMarkPaid?: (invoice: InvoiceTrackingResponse) => void;
  onIncreaseDunning?: (invoice: InvoiceTrackingResponse) => void;
  onViewDetails?: (invoice: InvoiceTrackingResponse) => void;
}

export function InvoiceActions({
  invoice,
  onMarkPaid,
  onIncreaseDunning,
  onViewDetails,
}: InvoiceActionsProps) {
  const isPaid = invoice.status === 'paid';
  const isCancelled = invoice.status === 'cancelled';
  const isMaxDunningLevel = invoice.dunningLevel >= 4;

  // Keine Aktionen für bezahlte oder stornierte Rechnungen
  const canMarkPaid = !isPaid && !isCancelled;
  const canIncreaseDunning = !isPaid && !isCancelled && !isMaxDunningLevel;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="h-8 w-8">
          <MoreHorizontal className="h-4 w-4" />
          <span className="sr-only">Aktionen öffnen</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {/* Details anzeigen */}
        {onViewDetails && (
          <DropdownMenuItem onClick={() => onViewDetails(invoice)}>
            <Eye className="h-4 w-4 mr-2" />
            {UI_LABELS.actionViewDetails}
          </DropdownMenuItem>
        )}

        {(onMarkPaid || onIncreaseDunning) && onViewDetails && (
          <DropdownMenuSeparator />
        )}

        {/* Als bezahlt markieren */}
        {onMarkPaid && canMarkPaid && (
          <DropdownMenuItem
            onClick={() => onMarkPaid(invoice)}
            className="text-green-600"
          >
            <CheckCircle className="h-4 w-4 mr-2" />
            {UI_LABELS.actionMarkPaid}
          </DropdownMenuItem>
        )}

        {/* Mahnstufe erhöhen */}
        {onIncreaseDunning && canIncreaseDunning && (
          <DropdownMenuItem
            onClick={() => onIncreaseDunning(invoice)}
            className="text-orange-600"
          >
            <TrendingUp className="h-4 w-4 mr-2" />
            {UI_LABELS.actionIncreaseDunning}
          </DropdownMenuItem>
        )}

        {/* Status-Hinweis für deaktivierte Aktionen */}
        {isPaid && (
          <DropdownMenuItem disabled className="text-muted-foreground">
            <CheckCircle className="h-4 w-4 mr-2" />
            Bereits bezahlt
          </DropdownMenuItem>
        )}

        {isCancelled && (
          <DropdownMenuItem disabled className="text-muted-foreground">
            <XCircle className="h-4 w-4 mr-2" />
            Storniert
          </DropdownMenuItem>
        )}

        {isMaxDunningLevel && !isPaid && !isCancelled && (
          <DropdownMenuItem disabled className="text-muted-foreground">
            <TrendingUp className="h-4 w-4 mr-2" />
            Max. Mahnstufe erreicht
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
