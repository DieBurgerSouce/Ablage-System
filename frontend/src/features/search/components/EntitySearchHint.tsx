/**
 * EntitySearchHint Component
 *
 * Zeigt an, wenn ein Dokument über eine Entity-Verknüpfung gefunden wurde.
 * "Gefunden als Kunde: Mueller GmbH (Kd-Nr. 12345)"
 */

import { Link } from '@tanstack/react-router';
import { Building2, Truck, Hash, CreditCard, FileText, User } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import type { MatchedEntity } from './SearchResultCard';

interface EntitySearchHintProps {
    entity: MatchedEntity;
    className?: string;
    compact?: boolean;
}

const matchTypeLabels: Record<string, string> = {
    name: 'Name',
    customer_number: 'Kundennummer',
    supplier_number: 'Lieferantennummer',
    matchcode: 'Matchcode',
    iban: 'IBAN',
    vat_id: 'USt-IdNr.',
};

const matchTypeIcons: Record<string, typeof Building2> = {
    name: FileText,
    customer_number: Hash,
    supplier_number: Hash,
    matchcode: User,
    iban: CreditCard,
    vat_id: FileText,
};

/**
 * Zeigt Entity-Match-Information für ein Suchergebnis.
 */
export function EntitySearchHint({ entity, className, compact = false }: EntitySearchHintProps) {
    const isCustomer = entity.entityType === 'customer';
    const Icon = isCustomer ? Building2 : Truck;
    const MatchIcon = matchTypeIcons[entity.matchType] || FileText;

    const entityLabel = isCustomer ? 'Kunde' : 'Lieferant';
    const entityNumber = isCustomer ? entity.customerNumber : entity.supplierNumber;
    const matchTypeLabel = matchTypeLabels[entity.matchType] || entity.matchType;

    const confidencePercent = Math.round(entity.matchConfidence * 100);

    // Compact version - just a badge
    if (compact) {
        return (
            <TooltipProvider>
                <Tooltip>
                    <TooltipTrigger asChild>
                        <Link
                            to={isCustomer ? '/relationships/customers/$entityId' : '/relationships/suppliers/$entityId'}
                            params={{ entityId: entity.entityId }}
                            className="inline-flex"
                            onClick={(e) => e.stopPropagation()}
                        >
                            <Badge
                                variant="outline"
                                className={cn(
                                    'gap-1 text-xs cursor-pointer hover:bg-muted',
                                    isCustomer
                                        ? 'border-blue-200 text-blue-700 bg-blue-50/50'
                                        : 'border-amber-200 text-amber-700 bg-amber-50/50',
                                    className
                                )}
                            >
                                <Icon className="h-3 w-3" />
                                <span className="truncate max-w-24">{entity.entityName}</span>
                            </Badge>
                        </Link>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs">
                        <div className="space-y-1">
                            <p className="font-medium">
                                Gefunden als {entityLabel}: {entity.entityName}
                            </p>
                            <p className="text-xs text-muted-foreground">
                                Erkannt via {matchTypeLabel} ({confidencePercent}% Konfidenz)
                            </p>
                            {entityNumber && (
                                <p className="text-xs">
                                    {isCustomer ? 'Kd-Nr.' : 'Lief-Nr.'}: {entityNumber}
                                </p>
                            )}
                        </div>
                    </TooltipContent>
                </Tooltip>
            </TooltipProvider>
        );
    }

    // Full version - expandable card section
    return (
        <Link
            to={isCustomer ? '/relationships/customers/$entityId' : '/relationships/suppliers/$entityId'}
            params={{ entityId: entity.entityId }}
            className="block"
            onClick={(e) => e.stopPropagation()}
        >
            <div
                className={cn(
                    'flex items-center gap-2 p-2 rounded-md text-sm transition-colors',
                    isCustomer
                        ? 'bg-blue-50/50 border border-blue-200/50 hover:bg-blue-50'
                        : 'bg-amber-50/50 border border-amber-200/50 hover:bg-amber-50',
                    className
                )}
            >
                <div
                    className={cn(
                        'p-1.5 rounded-md',
                        isCustomer ? 'bg-blue-100 text-blue-700' : 'bg-amber-100 text-amber-700'
                    )}
                >
                    <Icon className="h-4 w-4" />
                </div>

                <div className="flex-1 min-w-0">
                    <p
                        className={cn(
                            'font-medium truncate',
                            isCustomer ? 'text-blue-900' : 'text-amber-900'
                        )}
                    >
                        {entity.entityName}
                    </p>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <span className="flex items-center gap-1">
                            <MatchIcon className="h-3 w-3" />
                            {matchTypeLabel}
                        </span>
                        {entityNumber && (
                            <>
                                <span className="text-muted-foreground/50">·</span>
                                <span>{isCustomer ? 'Kd' : 'Lief'}-Nr. {entityNumber}</span>
                            </>
                        )}
                    </div>
                </div>

                <Badge
                    variant="secondary"
                    className={cn(
                        'text-xs shrink-0',
                        confidencePercent >= 90
                            ? 'bg-green-100 text-green-700'
                            : confidencePercent >= 70
                            ? 'bg-yellow-100 text-yellow-700'
                            : 'bg-gray-100 text-gray-600'
                    )}
                >
                    {confidencePercent}%
                </Badge>
            </div>
        </Link>
    );
}

export default EntitySearchHint;
