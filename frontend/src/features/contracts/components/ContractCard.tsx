/**
 * ContractCard - Vertragskarte mit Status-Badges und Countdown
 *
 * Zeigt:
 * - Vertrags-Titel und Nummer
 * - Status-Badge mit Farbcodierung
 * - Vertragspartner
 * - Kuendigungsfrist-Countdown
 * - Vertragsende-Countdown
 * - Quick-Actions
 */

import { format } from 'date-fns';
import { de } from 'date-fns/locale';
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import {
  MoreHorizontal,
  Eye,
  Edit,
  Trash2,
  Calendar,
  Clock,
  AlertTriangle,
  Building2,
  Euro,
  RefreshCw,
  Bell,
} from 'lucide-react';
import type { Contract } from '../types/contract-types';
import {
  ContractStatus,
  ContractType,
  CONTRACT_STATUS_LABELS,
  CONTRACT_TYPE_LABELS,
} from '../types/contract-types';

interface ContractCardProps {
  contract: Contract;
  onView: (contract: Contract) => void;
  onEdit: (contract: Contract) => void;
  onDelete: (contract: Contract) => void;
}

const statusConfig: Record<
  ContractStatus,
  { color: string; bgColor: string; borderColor: string }
> = {
  [ContractStatus.DRAFT]: {
    color: 'text-gray-700',
    bgColor: 'bg-gray-100',
    borderColor: 'border-gray-300',
  },
  [ContractStatus.PENDING_SIGNATURE]: {
    color: 'text-blue-700',
    bgColor: 'bg-blue-100',
    borderColor: 'border-blue-300',
  },
  [ContractStatus.ACTIVE]: {
    color: 'text-green-700',
    bgColor: 'bg-green-100',
    borderColor: 'border-green-300',
  },
  [ContractStatus.SUSPENDED]: {
    color: 'text-gray-700',
    bgColor: 'bg-gray-100',
    borderColor: 'border-gray-300',
  },
  [ContractStatus.EXPIRING_SOON]: {
    color: 'text-orange-700',
    bgColor: 'bg-orange-100',
    borderColor: 'border-orange-300',
  },
  [ContractStatus.EXPIRED]: {
    color: 'text-red-700',
    bgColor: 'bg-red-100',
    borderColor: 'border-red-300',
  },
  [ContractStatus.TERMINATED]: {
    color: 'text-gray-700',
    bgColor: 'bg-gray-100',
    borderColor: 'border-gray-300',
  },
  [ContractStatus.RENEWED]: {
    color: 'text-blue-700',
    bgColor: 'bg-blue-100',
    borderColor: 'border-blue-300',
  },
};

function formatCurrency(value?: number): string {
  if (value === undefined || value === null) return '-';
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

function formatDate(dateString?: string): string {
  if (!dateString) return '-';
  return format(new Date(dateString), 'dd.MM.yyyy', { locale: de });
}

function CountdownBadge({
  days,
  label,
  isCritical,
  icon: Icon,
}: {
  days: number;
  label: string;
  isCritical: boolean;
  icon: React.ElementType;
}) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div
            className={`flex items-center gap-1 px-2 py-1 rounded-md text-xs ${
              isCritical
                ? 'bg-red-100 text-red-700'
                : days <= 30
                ? 'bg-orange-100 text-orange-700'
                : 'bg-muted text-muted-foreground'
            }`}
          >
            <Icon className="h-3 w-3" />
            <span className="font-medium">{days}d</span>
          </div>
        </TooltipTrigger>
        <TooltipContent>
          <p>
            {label}: {days} Tage verbleibend
          </p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export function ContractCard({ contract, onView, onEdit, onDelete }: ContractCardProps) {
  const statusConf = statusConfig[contract.status as ContractStatus];
  const partyName = contract.party_b_name || contract.party_b?.name;

  return (
    <Card
      className={`cursor-pointer hover:shadow-md transition-shadow border-l-4 ${statusConf.borderColor}`}
      onClick={() => onView(contract)}
    >
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="space-y-1 min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <Badge className={`${statusConf.bgColor} ${statusConf.color} shrink-0`}>
                {CONTRACT_STATUS_LABELS[contract.status as ContractStatus]}
              </Badge>
              {contract.auto_renewal && (
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <RefreshCw className="h-3.5 w-3.5 text-blue-500" />
                    </TooltipTrigger>
                    <TooltipContent>
                      <p>Automatische Verlaengerung aktiv</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              )}
            </div>
            <h3 className="font-semibold text-sm truncate">{contract.title}</h3>
            <p className="text-xs text-muted-foreground font-mono">
              {contract.contract_number}
            </p>
          </div>

          <DropdownMenu>
            <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
              <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0">
                <MoreHorizontal className="h-4 w-4" />
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
        </div>
      </CardHeader>

      <CardContent className="pb-3 space-y-3">
        {/* Vertragstyp und Partner */}
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">
            {CONTRACT_TYPE_LABELS[contract.contract_type as ContractType]}
          </span>
          {partyName && (
            <span className="flex items-center gap-1 text-muted-foreground truncate max-w-[50%]">
              <Building2 className="h-3 w-3 shrink-0" />
              {partyName}
            </span>
          )}
        </div>

        {/* Laufzeit */}
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Calendar className="h-3 w-3" />
          <span>
            {formatDate(contract.start_date)}
            {contract.end_date && ` - ${formatDate(contract.end_date)}`}
          </span>
        </div>

        {/* Wert */}
        {(contract.total_value || contract.monthly_value) && (
          <div className="flex items-center gap-2 text-xs">
            <Euro className="h-3 w-3 text-muted-foreground" />
            <span className="font-medium">{formatCurrency(contract.total_value)}</span>
            {contract.monthly_value && (
              <span className="text-muted-foreground">
                ({formatCurrency(contract.monthly_value)}/Monat)
              </span>
            )}
          </div>
        )}
      </CardContent>

      <CardFooter className="pt-0 pb-3">
        {/* Countdown-Badges */}
        <div className="flex flex-wrap gap-2">
          {contract.days_until_notice_deadline !== undefined &&
            contract.days_until_notice_deadline >= 0 && (
              <CountdownBadge
                days={contract.days_until_notice_deadline}
                label="Kuendigungsfrist"
                isCritical={contract.is_notice_deadline_critical}
                icon={Bell}
              />
            )}
          {contract.days_until_end !== undefined && contract.days_until_end >= 0 && (
            <CountdownBadge
              days={contract.days_until_end}
              label="Vertragsende"
              isCritical={contract.is_expiring_soon}
              icon={Clock}
            />
          )}
          {contract.is_expiring_soon && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <AlertTriangle className="h-4 w-4 text-orange-500" />
                </TooltipTrigger>
                <TooltipContent>
                  <p>Vertrag laeuft bald ab</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
        </div>
      </CardFooter>
    </Card>
  );
}

export default ContractCard;
