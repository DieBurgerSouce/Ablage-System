/**
 * Missed Skonto Table
 * Tabelle mit verpassten Skonto-Möglichkeiten
 */

import { Link } from '@tanstack/react-router';
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
import { Skeleton } from '@/components/ui/skeleton';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { ExternalLink, AlertCircle, ChevronLeft, ChevronRight } from 'lucide-react';
import { formatCurrency, formatDate } from '@/features/banking/utils/format';
import type { MissedSkontoItem } from '../types';

interface MissedSkontoTableProps {
  items?: MissedSkontoItem[];
  isLoading?: boolean;
  total?: number;
  page?: number;
  perPage?: number;
  onPageChange?: (page: number) => void;
}

export function MissedSkontoTable({
  items = [],
  isLoading,
  total = 0,
  page = 1,
  perPage = 20,
  onPageChange,
}: MissedSkontoTableProps) {
  const totalPages = Math.ceil(total / perPage);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <AlertCircle className="h-12 w-12 text-muted-foreground/50 mb-4" />
        <h3 className="text-lg font-semibold">Keine verpassten Skonto-Möglichkeiten</h3>
        <p className="text-muted-foreground max-w-md">
          Im ausgewählten Zeitraum wurden keine Skonto-Fristen verpasst. Sehr gut!
        </p>
      </div>
    );
  }

  const getSeverityBadge = (daysMissedBy: number) => {
    if (daysMissedBy <= 3) {
      return <Badge variant="outline">+{daysMissedBy} Tage</Badge>;
    }
    if (daysMissedBy <= 7) {
      return <Badge variant="secondary">+{daysMissedBy} Tage</Badge>;
    }
    return <Badge variant="destructive">+{daysMissedBy} Tage</Badge>;
  };

  return (
    <div className="space-y-4">
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Rechnung</TableHead>
              <TableHead>Lieferant/Kunde</TableHead>
              <TableHead className="text-right">Betrag</TableHead>
              <TableHead className="text-right">Skonto</TableHead>
              <TableHead>Frist</TableHead>
              <TableHead>Verpasst um</TableHead>
              <TableHead className="text-right">Verpasste Ersparnis</TableHead>
              <TableHead className="w-[50px]"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.invoiceId}>
                <TableCell className="font-medium">
                  {item.invoiceNumber || 'Keine Nr.'}
                </TableCell>
                <TableCell>
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className="truncate max-w-[200px] block">
                          {item.entityName}
                        </span>
                      </TooltipTrigger>
                      <TooltipContent>{item.entityName}</TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </TableCell>
                <TableCell className="text-right">
                  {formatCurrency(item.amount)}
                </TableCell>
                <TableCell className="text-right">
                  <span className="text-muted-foreground">
                    {item.skontoPercentage}%
                  </span>
                </TableCell>
                <TableCell>{formatDate(item.skontoDeadline)}</TableCell>
                <TableCell>{getSeverityBadge(item.daysMissedBy)}</TableCell>
                <TableCell className="text-right font-semibold text-red-600">
                  {formatCurrency(item.skontoAmount)}
                </TableCell>
                <TableCell>
                  {item.documentId && (
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button variant="ghost" size="icon" asChild>
                            <Link
                              to="/documents/$documentId"
                              params={{ documentId: item.documentId }}
                            >
                              <ExternalLink className="h-4 w-4" />
                            </Link>
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Dokument öffnen</TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Zeige {(page - 1) * perPage + 1} bis {Math.min(page * perPage, total)} von{' '}
            {total} Einträgen
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => onPageChange?.(page - 1)}
            >
              <ChevronLeft className="h-4 w-4 mr-1" />
              Zurück
            </Button>
            <span className="text-sm">
              Seite {page} von {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => onPageChange?.(page + 1)}
            >
              Weiter
              <ChevronRight className="h-4 w-4 ml-1" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
