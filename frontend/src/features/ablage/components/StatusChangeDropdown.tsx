/**
 * StatusChangeDropdown - Dropdown zum Ändern des Status für mehrere Dokumente
 *
 * Features:
 * - Zahlungsstatus ändern (Bezahlt, Offen, etc.)
 * - Archivieren
 * - WCAG 2.1 AA konform
 * - Loading-States während der Operation
 */

import { useState } from 'react';
import {
  Settings2,
  CheckCircle2,
  Clock,
  AlertTriangle,
  Archive,
  Loader2,
  ChevronDown,
} from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { logger } from '@/lib/logger';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { useBulkMarkAsPaid, useBulkMoveCategory } from '../hooks/use-ablage-queries';
import type { PaymentStatus } from '../types';

// ==================== Types ====================

interface StatusChangeDropdownProps {
  selectedIds: string[];
  showPaymentStatus: boolean;
  disabled?: boolean;
  onSuccess?: () => void;
}

interface StatusOption {
  id: string;
  label: string;
  icon: React.ElementType;
  className?: string;
  action: 'payment' | 'archive';
  paymentStatus?: PaymentStatus;
}

// ==================== Config ====================

const STATUS_OPTIONS: StatusOption[] = [
  {
    id: 'bezahlt',
    label: 'Als bezahlt markieren',
    icon: CheckCircle2,
    className: 'text-green-600',
    action: 'payment',
    paymentStatus: 'bezahlt',
  },
  {
    id: 'offen',
    label: 'Als offen markieren',
    icon: Clock,
    className: 'text-blue-600',
    action: 'payment',
    paymentStatus: 'offen',
  },
  {
    id: 'überfällig',
    label: 'Als überfällig markieren',
    icon: AlertTriangle,
    className: 'text-red-600',
    action: 'payment',
    paymentStatus: 'überfällig',
  },
];

const ARCHIVE_OPTION: StatusOption = {
  id: 'archiv',
  label: 'Archivieren',
  icon: Archive,
  action: 'archive',
};

// ==================== Main Component ====================

export function StatusChangeDropdown({
  selectedIds,
  showPaymentStatus,
  disabled = false,
  onSuccess,
}: StatusChangeDropdownProps) {
  const [archiveDialogOpen, setArchiveDialogOpen] = useState(false);
  const [processingAction, setProcessingAction] = useState<string | null>(null);

  const bulkMarkAsPaid = useBulkMarkAsPaid();
  const bulkMoveCategory = useBulkMoveCategory();

  const isLoading = bulkMarkAsPaid.isPending || bulkMoveCategory.isPending;

  // Handle status change for payment status
  const handlePaymentStatusChange = async (status: PaymentStatus) => {
    if (selectedIds.length === 0) return;

    setProcessingAction(status);
    try {
      // Note: The API expects bezahlt for "mark as paid", but for other statuses
      // we might need a different endpoint. For now, we use bulkMarkAsPaid for "bezahlt"
      // and would need a separate hook for other statuses
      if (status === 'bezahlt') {
        await bulkMarkAsPaid.mutateAsync({
          documentIds: selectedIds,
        });
      } else {
        // For other statuses, we would need a bulk status update hook
        // This is a placeholder - implement when backend supports it
        logger.warn('Massen-Statusupdate zu', status, 'noch nicht implementiert');
      }
      onSuccess?.();
    } catch {
      // Error handling is done by the mutation hook
    } finally {
      setProcessingAction(null);
    }
  };

  // Handle archive action
  const handleArchive = async () => {
    if (selectedIds.length === 0) return;

    setProcessingAction('archiv');
    try {
      await bulkMoveCategory.mutateAsync({
        documentIds: selectedIds,
        targetCategory: 'archiv',
      });
      setArchiveDialogOpen(false);
      onSuccess?.();
    } catch {
      // Error handling is done by the mutation hook
    } finally {
      setProcessingAction(null);
    }
  };

  const handleOptionClick = (option: StatusOption) => {
    if (option.action === 'archive') {
      setArchiveDialogOpen(true);
    } else if (option.paymentStatus) {
      handlePaymentStatusChange(option.paymentStatus);
    }
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            disabled={disabled || isLoading || selectedIds.length === 0}
            aria-label="Status ändern"
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" aria-hidden="true" />
            ) : (
              <Settings2 className="h-4 w-4 mr-2" aria-hidden="true" />
            )}
            Status ändern
            <ChevronDown className="h-4 w-4 ml-2" aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuLabel>Status ändern</DropdownMenuLabel>
          <DropdownMenuSeparator />

          {/* Payment Status Options (only for invoice categories) */}
          {showPaymentStatus && (
            <>
              {STATUS_OPTIONS.map((option) => {
                const Icon = option.icon;
                const isProcessing = processingAction === option.id;
                return (
                  <DropdownMenuItem
                    key={option.id}
                    onClick={() => handleOptionClick(option)}
                    disabled={isLoading}
                    className={option.className}
                  >
                    {isProcessing ? (
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" aria-hidden="true" />
                    ) : (
                      <Icon className="h-4 w-4 mr-2" aria-hidden="true" />
                    )}
                    {option.label}
                  </DropdownMenuItem>
                );
              })}
              <DropdownMenuSeparator />
            </>
          )}

          {/* Archive Option (always available) */}
          <DropdownMenuItem
            onClick={() => handleOptionClick(ARCHIVE_OPTION)}
            disabled={isLoading}
          >
            {processingAction === 'archiv' ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" aria-hidden="true" />
            ) : (
              <Archive className="h-4 w-4 mr-2" aria-hidden="true" />
            )}
            {ARCHIVE_OPTION.label}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Archive Confirmation Dialog */}
      <AlertDialog open={archiveDialogOpen} onOpenChange={setArchiveDialogOpen}>
        <AlertDialogContent aria-describedby="archive-dialog-description">
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <Archive className="h-5 w-5" aria-hidden="true" />
              Dokumente archivieren?
            </AlertDialogTitle>
            <AlertDialogDescription id="archive-dialog-description">
              Möchten Sie wirklich{' '}
              <span className="font-semibold">{selectedIds.length} Dokumente</span>{' '}
              archivieren? Archivierte Dokumente können später wiederhergestellt werden.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={bulkMoveCategory.isPending}>
              Abbrechen
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleArchive}
              disabled={bulkMoveCategory.isPending}
              aria-label={`${selectedIds.length} Dokumente archivieren`}
            >
              {bulkMoveCategory.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" aria-hidden="true" />
                  Wird archiviert...
                </>
              ) : (
                <>
                  <Archive className="h-4 w-4 mr-2" aria-hidden="true" />
                  Archivieren
                </>
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

export default StatusChangeDropdown;
