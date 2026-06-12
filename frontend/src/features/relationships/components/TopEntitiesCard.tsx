/**
 * TopEntitiesCard Component
 *
 * Zeigt die Top-Kunden oder Top-Lieferanten mit Dokumentanzahl.
 * Klickbar für Navigation zur Entity-Detail-Seite.
 */

import { useNavigate } from '@tanstack/react-router';
import { Users, Truck, FileText, Clock, ChevronRight, type LucideIcon } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { TopEntity } from '../api/relationships-api';

// ==================== Types ====================

interface TopEntitiesCardProps {
    title: string;
    description?: string;
    entities: TopEntity[];
    type: 'customer' | 'supplier';
    maxItems?: number;
    showRank?: boolean;
}

// ==================== Helper Functions ====================

function formatRelativeTime(timestamp: string | null): string {
    if (!timestamp) return '—';

    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return 'Heute';
    if (diffDays === 1) return 'Gestern';
    if (diffDays < 7) return `Vor ${diffDays} Tagen`;
    if (diffDays < 30) return `Vor ${Math.floor(diffDays / 7)} Wochen`;
    return `Vor ${Math.floor(diffDays / 30)} Monaten`;
}

// ==================== Entity Row ====================

interface EntityRowProps {
    entity: TopEntity;
    rank: number;
    type: 'customer' | 'supplier';
    showRank: boolean;
    onClick: () => void;
}

function EntityRow({ entity, rank, type, showRank, onClick }: EntityRowProps) {
    return (
        <div
            className={cn(
                'flex items-center gap-3 py-2.5 px-3 -mx-3 rounded-md',
                'hover:bg-accent/50 cursor-pointer transition-colors group'
            )}
            onClick={onClick}
        >
            {/* Rank */}
            {showRank && (
                <div
                    className={cn(
                        'w-6 h-6 rounded-full flex items-center justify-center text-xs font-semibold shrink-0',
                        rank === 1 && 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
                        rank === 2 && 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
                        rank === 3 && 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
                        rank > 3 && 'bg-muted text-muted-foreground'
                    )}
                >
                    {rank}
                </div>
            )}

            {/* Entity Info */}
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                    <span className="font-medium truncate">{entity.name}</span>
                    {(type === 'customer' ? entity.customerNumber : entity.supplierNumber) && (
                        <Badge variant="outline" className="text-[10px] h-4 shrink-0">
                            {type === 'customer' ? entity.customerNumber : entity.supplierNumber}
                        </Badge>
                    )}
                </div>
                <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
                    <span className="flex items-center gap-1">
                        <FileText className="h-3 w-3" />
                        {entity.documentCount} Dokumente
                    </span>
                    <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {formatRelativeTime(entity.lastActivity)}
                    </span>
                </div>
            </div>

            {/* Chevron */}
            <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
        </div>
    );
}

// ==================== Component ====================

export function TopEntitiesCard({
    title,
    description,
    entities,
    type,
    maxItems = 10,
    showRank = true,
}: TopEntitiesCardProps) {
    const navigate = useNavigate();
    const Icon: LucideIcon = type === 'customer' ? Users : Truck;

    const handleEntityClick = (entityId: string) => {
        if (type === 'customer') {
            navigate({ to: '/ablage/kunden/$entityId', params: { entityId } });
        } else {
            navigate({ to: '/ablage/lieferanten/$entityId', params: { entityId } });
        }
    };

    const displayedEntities = entities.slice(0, maxItems);
    const totalDocuments = entities.reduce((sum, e) => sum + e.documentCount, 0);

    return (
        <Card>
            <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                    <div>
                        <CardTitle className="text-lg flex items-center gap-2">
                            <Icon className="h-5 w-5" />
                            {title}
                        </CardTitle>
                        {description && (
                            <CardDescription>{description}</CardDescription>
                        )}
                    </div>
                    <Badge variant="secondary" className="text-xs">
                        {totalDocuments} Dokumente
                    </Badge>
                </div>
            </CardHeader>
            <CardContent>
                {displayedEntities.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-8 text-center">
                        <Icon className="h-10 w-10 text-muted-foreground mb-3" />
                        <p className="text-muted-foreground text-sm">
                            Keine {type === 'customer' ? 'Kunden' : 'Lieferanten'} im Zeitraum
                        </p>
                    </div>
                ) : (
                    <div className="space-y-0.5">
                        {displayedEntities.map((entity, index) => (
                            <EntityRow
                                key={entity.id}
                                entity={entity}
                                rank={index + 1}
                                type={type}
                                showRank={showRank}
                                onClick={() => handleEntityClick(entity.id)}
                            />
                        ))}
                    </div>
                )}
            </CardContent>
        </Card>
    );
}

export default TopEntitiesCard;
