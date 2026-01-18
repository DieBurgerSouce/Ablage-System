/**
 * ContractTable - Vertrags-Tabelle mit Sortierung und Aktionen
 *
 * Features:
 * - Sortierbare Spalten
 * - Status-Badges mit Farbcodierung
 * - Inline-Aktionen
 * - Responsive Design
 */

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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  MoreHorizontal,
  Eye,
  Edit,
  Trash2,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  RefreshCw,
} from 'lucide-react';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';
import type { Contract, ContractListParams } from '../types/contract-types';
import {
  ContractStatus,
  ContractType,
  CONTRACT_STATUS_LABELS,
  CONTRACT_TYPE_LABELS,
} from '../types/contract-types';

interface ContractTableProps {
  contracts: Contract[];
  isLoading: boolean;
  sortBy?: ContractListParams['order_by'];
  sortDir?: ContractListParams['order_dir'];
  onSort: (column: ContractListParams['order_by']) => void;
  onView: (contract: Contract) => void;
  onEdit: (contract: Contract) => void;
  onDelete: (contract: Contract) => void;
  onRenewal?: (contract: Contract) => void;
}

const statusConfig: Record<
  ContractStatus,
  { variant: 'default' | 'secondary' | 'destructive' | 'outline'; className?: string }
> = {
  [ContractStatus.DRAFT]: { variant: 'secondary' },
  [ContractStatus.PENDING_SIGNATURE]: { variant: 'outline', className: 'border-blue-500 text-blue-700' },
  [ContractStatus.ACTIVE]: { variant: 'default', className: 'bg-green-500' },
  [ContractStatus.SUSPENDED]: { variant: 'secondary', className: 'bg-gray-500' },
  [ContractStatus.EXPIRING_SOON]: { variant: 'outline', className: 'border-orange-500 text-orange-700' },
  [ContractStatus.EXPIRED]: { variant: 'destructive' },
  [ContractStatus.TERMINATED]: { variant: 'destructive', className: 'bg-gray-600' },
  [ContractStatus.RENEWED]: { variant: 'default', className: 'bg-blue-500' },
};

function SortHeader({
  column,
  label,
  currentSort,
  currentDir,
  onSort,
}: {
  column: ContractListParams['order_by'];
  label: string;
  currentSort?: ContractListParams['order_by'];
  currentDir?: ContractListParams['order_dir'];
  onSort: (column: ContractListParams['order_by']) => void;
}) {
  const isActive = currentSort === column;

  return (
    <Button
      variant="ghost"
      size="sm"
      className="-ml-3 h-8 hover:bg-transparent"
      onClick={() => onSort(column)}
    >
      {label}
      {isActive ? (
        currentDir === 'asc' ? (
          <ArrowUp className="ml-2 h-4 w-4" />
        ) : (
          <ArrowDown className="ml-2 h-4 w-4" />
        )
      ) : (
        <ArrowUpDown className="ml-2 h-4 w-4 opacity-50" />
      )}
    </Button>
  );
}

function formatCurrency(value?: number): string {
  if (value === undefined || value === null) return '-';
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(value);
}

function formatDate(dateString?: string): string {
  if (!dateString) return '-';
  return format(new Date(dateString), 'dd.MM.yyyy', { locale: de });
}

export function ContractTable({
  contracts,
  isLoading,
  sortBy,
  sortDir,
  onSort,
  onView,
  onEdit,
  onDelete,
  onRenewal,
}: ContractTableProps) {
  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    );
  }

  if (contracts.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <p>Keine Vertraege gefunden</p>
      </div>
    );
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[120px]">
              <SortHeader
                column="contract_number"
                label="Vertragsnr."
                currentSort={sortBy}
                currentDir={sortDir}
                onSort={onSort}
              />
            </TableHead>
            <TableHead>
              <SortHeader
                column="title"
                label="Titel"
                currentSort={sortBy}
                currentDir={sortDir}
                onSort={onSort}
              />
            </TableHead>
            <TableHead>Typ</TableHead>
            <TableHead>Partner</TableHead>
            <TableHead>
              <SortHeader
                column="end_date"
                label="Laufzeit"
                currentSort={sortBy}
                currentDir={sortDir}
                onSort={onSort}
              />
            </TableHead>
            <TableHead>
              <SortHeader
                column="notice_deadline"
                label="Kuendigungsfrist"
                currentSort={sortBy}
                currentDir={sortDir}
                onSort={onSort}
              />
            </TableHead>
            <TableHead className="text-right">
              <SortHeader
                column="total_value"
                label="Wert"
                currentSort={sortBy}
                currentDir={sortDir}
                onSort={onSort}
              />
            </TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="w-[50px]"></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {contracts.map((contract) => {
            const statusConf = statusConfig[contract.status];
            const showRenewalAction =
              contract.status === ContractStatus.ACTIVE &&
              contract.is_expiring_soon &&
              contract.auto_renewal === false;

            return (
              <TableRow
                key={contract.id}
                className="cursor-pointer"
                onClick={() => onView(contract)}
              >
                <TableCell className="font-mono text-sm">
                  {contract.contract_number}
                </TableCell>
                <TableCell className="font-medium max-w-[250px] truncate">
                  {contract.title}
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {CONTRACT_TYPE_LABELS[contract.contract_type as ContractType] ||
                    contract.contract_type}
                </TableCell>
                <TableCell className="text-sm">
                  {contract.party_b_name || contract.party_b?.name || '-'}
                </TableCell>
                <TableCell className="text-sm">
                  <div className="flex flex-col">
                    <span>{formatDate(contract.start_date)}</span>
                    {contract.end_date && (
                      <span className="text-muted-foreground">
                        bis {formatDate(contract.end_date)}
                      </span>
                    )}
                    {contract.days_until_end !== undefined && contract.days_until_end >= 0 && (
                      <span
                        className={`text-xs ${
                          contract.days_until_end <= 30
                            ? 'text-red-600'
                            : contract.days_until_end <= 90
                            ? 'text-orange-600'
                            : 'text-muted-foreground'
                        }`}
                      >
                        ({contract.days_until_end} Tage)
                      </span>
                    )}
                  </div>
                </TableCell>
                <TableCell className="text-sm">
                  {contract.notice_deadline ? (
                    <div className="flex flex-col">
                      <span
                        className={
                          contract.is_notice_deadline_critical ? 'text-red-600 font-medium' : ''
                        }
                      >
                        {formatDate(contract.notice_deadline)}
                      </span>
                      {contract.days_until_notice_deadline !== undefined && (
                        <span
                          className={`text-xs ${
                            contract.is_notice_deadline_critical
                              ? 'text-red-600'
                              : 'text-muted-foreground'
                          }`}
                        >
                          ({contract.days_until_notice_deadline} Tage)
                        </span>
                      )}
                    </div>
                  ) : (
                    '-'
                  )}
                </TableCell>
                <TableCell className="text-right font-medium">
                  {formatCurrency(contract.total_value)}
                  {contract.monthly_value && (
                    <div className="text-xs text-muted-foreground">
                      {formatCurrency(contract.monthly_value)}/Monat
                    </div>
                  )}
                </TableCell>
                <TableCell>
                  <Badge variant={statusConf.variant} className={statusConf.className}>
                    {CONTRACT_STATUS_LABELS[contract.status as ContractStatus] || contract.status}
                  </Badge>
                </TableCell>
                <TableCell>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                      <Button variant="ghost" size="icon" className="h-8 w-8">
                        <MoreHorizontal className="h-4 w-4" />
                        <span className="sr-only">Aktionen</span>
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onClick={() => onView(contract)}>
                        <Eye className="h-4 w-4 mr-2" />
                        Anzeigen
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => onEdit(contract)}>
                        <Edit className="h-4 w-4 mr-2" />
                        Bearbeiten
                      </DropdownMenuItem>
                      {showRenewalAction && onRenewal && (
                        <DropdownMenuItem onClick={() => onRenewal(contract)}>
                          <RefreshCw className="h-4 w-4 mr-2" />
                          Verlaengern
                        </DropdownMenuItem>
                      )}
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        className="text-destructive"
                        onClick={() => onDelete(contract)}
                      >
                        <Trash2 className="h-4 w-4 mr-2" />
                        Loeschen
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
