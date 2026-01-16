/**
 * EntityNode Component
 *
 * Custom React Flow Node fuer Geschaeftspartner im Entity-Graph.
 * Zeigt Name, Typ, Dokumentanzahl und Firmenzugehoerigkeit.
 */

import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { Users, Truck, FileText, Building2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { EntityNodeData } from '../api/relationships-api';

// ==================== Component ====================

function EntityNodeComponent({ data, selected }: NodeProps<{ data: EntityNodeData }>) {
    const nodeData = data as unknown as EntityNodeData;
    const isCustomer = nodeData.nodeType === 'customer';
    const Icon = isCustomer ? Users : Truck;

    // Firmen-Badges
    const companyBadges = nodeData.companyPresence.map((company) => {
        const label = company === 'folie' ? 'Folie' : company === 'messer' ? 'Messer' : company;
        const variant = company === 'folie' ? 'secondary' : 'outline';
        return { key: company, label, variant };
    });

    return (
        <div
            className={cn(
                'px-4 py-3 rounded-lg border-2 bg-background shadow-md min-w-[180px] max-w-[240px]',
                'transition-all duration-200',
                selected && 'ring-2 ring-ring ring-offset-2',
                isCustomer
                    ? 'border-blue-500/50 hover:border-blue-500'
                    : 'border-amber-500/50 hover:border-amber-500'
            )}
        >
            {/* Input Handle (links) */}
            <Handle
                type="target"
                position={Position.Left}
                className={cn(
                    'w-3 h-3 !bg-muted-foreground border-2 border-background',
                    isCustomer ? '!bg-blue-500' : '!bg-amber-500'
                )}
            />

            {/* Header mit Icon und Typ */}
            <div className="flex items-center gap-2 mb-2">
                <div
                    className={cn(
                        'w-8 h-8 rounded-full flex items-center justify-center',
                        isCustomer
                            ? 'bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400'
                            : 'bg-amber-100 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400'
                    )}
                >
                    <Icon className="h-4 w-4" />
                </div>
                <Badge
                    variant="outline"
                    className={cn(
                        'text-[10px] h-5',
                        isCustomer ? 'border-blue-500/50' : 'border-amber-500/50'
                    )}
                >
                    {isCustomer ? 'Kunde' : 'Lieferant'}
                </Badge>
            </div>

            {/* Name */}
            <div className="font-medium text-sm truncate mb-1.5" title={nodeData.name}>
                {nodeData.name}
            </div>

            {/* Kunden-/Lieferantennummer */}
            {(nodeData.customerNumber || nodeData.supplierNumber) && (
                <div className="text-xs text-muted-foreground mb-2">
                    {isCustomer ? nodeData.customerNumber : nodeData.supplierNumber}
                </div>
            )}

            {/* Statistiken */}
            <div className="flex items-center justify-between text-xs text-muted-foreground">
                <div className="flex items-center gap-1">
                    <FileText className="h-3 w-3" />
                    <span>{nodeData.documentCount}</span>
                </div>

                {/* Firmen-Badges */}
                <div className="flex gap-1">
                    {companyBadges.map((badge) => (
                        <Badge
                            key={badge.key}
                            variant={badge.variant as 'secondary' | 'outline'}
                            className="text-[9px] h-4 px-1.5"
                        >
                            {badge.label}
                        </Badge>
                    ))}
                </div>
            </div>

            {/* Output Handle (rechts) */}
            <Handle
                type="source"
                position={Position.Right}
                className={cn(
                    'w-3 h-3 !bg-muted-foreground border-2 border-background',
                    isCustomer ? '!bg-blue-500' : '!bg-amber-500'
                )}
            />
        </div>
    );
}

// ==================== Memoized Export ====================

export const EntityNode = memo(EntityNodeComponent);

export default EntityNode;
