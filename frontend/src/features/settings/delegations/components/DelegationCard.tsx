/**
 * DelegationCard Component
 *
 * Displays a single delegation with actions
 */

import { useState } from 'react';
import {
  User,
  Calendar,
  Clock,
  ChevronDown,
  ChevronUp,
  Check,
  X,
  RotateCcw,
  CalendarPlus,
  MoreHorizontal,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import type { Delegation } from '../types';
import {
  DelegationStatus,
  DELEGATION_TYPE_LABELS,
  DELEGATION_STATUS_LABELS,
  DELEGATION_REASON_LABELS,
} from '../types';

interface DelegationCardProps {
  delegation: Delegation;
  direction: 'given' | 'received';
  currentUserId: string;
  onAccept?: (id: string) => void;
  onDecline?: (id: string) => void;
  onRevoke?: (id: string) => void;
  onExtend?: (id: string) => void;
  isLoading?: boolean;
}

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

function getStatusVariant(
  status: DelegationStatus
): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (status) {
    case DelegationStatus.ACTIVE:
      return 'default';
    case DelegationStatus.PENDING:
      return 'secondary';
    case DelegationStatus.EXPIRED:
    case DelegationStatus.REVOKED:
    case DelegationStatus.DECLINED:
      return 'outline';
    default:
      return 'outline';
  }
}

function getDaysRemaining(endDate: string): number {
  const end = new Date(endDate);
  const now = new Date();
  const diffTime = end.getTime() - now.getTime();
  return Math.ceil(diffTime / (1000 * 60 * 60 * 24));
}

export function DelegationCard({
  delegation,
  direction,
  currentUserId,
  onAccept,
  onDecline,
  onRevoke,
  onExtend,
  isLoading = false,
}: DelegationCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const otherUser =
    direction === 'given' ? delegation.delegate : delegation.delegator;
  const otherUserName = otherUser?.display_name || otherUser?.email || 'Unbekannt';

  const isPending = delegation.status === DelegationStatus.PENDING;
  const isActive = delegation.status === DelegationStatus.ACTIVE;
  const canAcceptDecline = isPending && direction === 'received';
  const canRevoke = isActive && direction === 'given';
  const canExtend = isActive && direction === 'given';

  const daysRemaining = isActive ? getDaysRemaining(delegation.end_date) : null;

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-4">
          {/* Main Info */}
          <div className="flex items-start gap-3 flex-1 min-w-0">
            <div className="p-2 rounded-lg bg-muted">
              <User className="h-5 w-5" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-medium truncate">{otherUserName}</span>
                <Badge variant={getStatusVariant(delegation.status)}>
                  {DELEGATION_STATUS_LABELS[delegation.status]}
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground mt-0.5">
                {DELEGATION_TYPE_LABELS[delegation.delegation_type]}
                {' • '}
                {DELEGATION_REASON_LABELS[delegation.reason]}
              </p>
              <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  <Calendar className="h-3 w-3" />
                  {formatDate(delegation.start_date)} - {formatDate(delegation.end_date)}
                </span>
                {daysRemaining !== null && (
                  <span
                    className={`flex items-center gap-1 ${
                      daysRemaining <= 3 ? 'text-orange-600 dark:text-orange-400' : ''
                    }`}
                  >
                    <Clock className="h-3 w-3" />
                    {daysRemaining > 0
                      ? `${daysRemaining} Tage verbleibend`
                      : daysRemaining === 0
                      ? 'Endet heute'
                      : 'Abgelaufen'}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2">
            {canAcceptDecline && (
              <>
                <Button
                  size="sm"
                  onClick={() => onAccept?.(delegation.id)}
                  disabled={isLoading}
                >
                  <Check className="h-4 w-4 mr-1" />
                  Annehmen
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onDecline?.(delegation.id)}
                  disabled={isLoading}
                >
                  <X className="h-4 w-4 mr-1" />
                  Ablehnen
                </Button>
              </>
            )}

            {(canRevoke || canExtend) && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" disabled={isLoading}>
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {canExtend && (
                    <DropdownMenuItem onClick={() => onExtend?.(delegation.id)}>
                      <CalendarPlus className="h-4 w-4 mr-2" />
                      Verlaengern
                    </DropdownMenuItem>
                  )}
                  {canRevoke && (
                    <DropdownMenuItem
                      onClick={() => onRevoke?.(delegation.id)}
                      className="text-destructive"
                    >
                      <RotateCcw className="h-4 w-4 mr-2" />
                      Widerrufen
                    </DropdownMenuItem>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            )}

            {/* Expand/Collapse */}
            <Collapsible open={isExpanded} onOpenChange={setIsExpanded}>
              <CollapsibleTrigger asChild>
                <Button variant="ghost" size="icon">
                  {isExpanded ? (
                    <ChevronUp className="h-4 w-4" />
                  ) : (
                    <ChevronDown className="h-4 w-4" />
                  )}
                </Button>
              </CollapsibleTrigger>
            </Collapsible>
          </div>
        </div>

        {/* Expanded Details */}
        <Collapsible open={isExpanded} onOpenChange={setIsExpanded}>
          <CollapsibleContent>
            <div className="mt-4 pt-4 border-t space-y-3">
              {delegation.reason_details && (
                <div>
                  <span className="text-sm font-medium">Anmerkung:</span>
                  <p className="text-sm text-muted-foreground mt-1">
                    {delegation.reason_details}
                  </p>
                </div>
              )}

              {delegation.permissions && delegation.permissions.length > 0 && (
                <div>
                  <span className="text-sm font-medium">Berechtigungen:</span>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {delegation.permissions.map((perm) => (
                      <Badge key={perm} variant="outline" className="text-xs">
                        {perm}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-muted-foreground">Benachrichtigungen:</span>
                  <span className="ml-2">
                    {delegation.notify_on_action ? 'Aktiviert' : 'Deaktiviert'}
                  </span>
                </div>
                <div>
                  <span className="text-muted-foreground">Auto-Verlaengerung:</span>
                  <span className="ml-2">
                    {delegation.auto_extend
                      ? `Ja (max. ${delegation.max_extensions}x)`
                      : 'Nein'}
                  </span>
                </div>
                {delegation.extension_count > 0 && (
                  <div>
                    <span className="text-muted-foreground">Verlaengerungen:</span>
                    <span className="ml-2">{delegation.extension_count}</span>
                  </div>
                )}
                <div>
                  <span className="text-muted-foreground">Erstellt:</span>
                  <span className="ml-2">{formatDate(delegation.created_at)}</span>
                </div>
              </div>
            </div>
          </CollapsibleContent>
        </Collapsible>
      </CardContent>
    </Card>
  );
}
