/**
 * InvoicePagination - Pagination Controls für Rechnungsliste
 */

import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react';
import type { InvoiceFilter } from '../types/invoice-types';

interface InvoicePaginationProps {
  filter: Partial<InvoiceFilter>;
  onFilterChange: (filter: Partial<InvoiceFilter>) => void;
  totalItems: number;
  isLoading?: boolean;
}

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

export function InvoicePagination({
  filter,
  onFilterChange,
  totalItems,
  isLoading = false,
}: InvoicePaginationProps) {
  const currentPage = filter.page ?? 1;
  const perPage = filter.perPage ?? 20;
  const totalPages = Math.max(1, Math.ceil(totalItems / perPage));

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= totalPages) {
      onFilterChange({ ...filter, page: newPage });
    }
  };

  const handlePerPageChange = (value: string) => {
    const newPerPage = parseInt(value, 10);
    onFilterChange({ ...filter, perPage: newPerPage, page: 1 });
  };

  // Berechne angezeigte Items
  const startItem = totalItems === 0 ? 0 : (currentPage - 1) * perPage + 1;
  const endItem = Math.min(currentPage * perPage, totalItems);

  return (
    <div className="flex items-center justify-between px-2 py-4 border-t">
      {/* Linke Seite: Anzahl Einträge */}
      <div className="flex items-center gap-4 text-sm text-muted-foreground">
        <span>
          {totalItems === 0 ? (
            'Keine Einträge'
          ) : (
            <>
              {startItem}–{endItem} von {totalItems} Einträgen
            </>
          )}
        </span>

        {/* Per Page Selector */}
        <div className="flex items-center gap-2">
          <span>Pro Seite:</span>
          <Select
            value={perPage.toString()}
            onValueChange={handlePerPageChange}
            disabled={isLoading}
          >
            <SelectTrigger className="w-[70px] h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PAGE_SIZE_OPTIONS.map((size) => (
                <SelectItem key={size} value={size.toString()}>
                  {size}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Rechte Seite: Navigation */}
      <div className="flex items-center gap-1">
        {/* Erste Seite */}
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={() => handlePageChange(1)}
          disabled={currentPage === 1 || isLoading}
          aria-label="Erste Seite"
        >
          <ChevronsLeft className="h-4 w-4" />
        </Button>

        {/* Vorherige Seite */}
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={() => handlePageChange(currentPage - 1)}
          disabled={currentPage === 1 || isLoading}
          aria-label="Vorherige Seite"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>

        {/* Seitenanzeige */}
        <span className="px-3 text-sm font-medium">
          Seite {currentPage} von {totalPages}
        </span>

        {/* Nächste Seite */}
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={() => handlePageChange(currentPage + 1)}
          disabled={currentPage === totalPages || isLoading}
          aria-label="Nächste Seite"
        >
          <ChevronRight className="h-4 w-4" />
        </Button>

        {/* Letzte Seite */}
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={() => handlePageChange(totalPages)}
          disabled={currentPage === totalPages || isLoading}
          aria-label="Letzte Seite"
        >
          <ChevronsRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
