/**
 * Daily Agenda Card Component
 *
 * Zeigt Tagesagenda-Einträge gruppiert nach Typ an.
 */

import { memo, useMemo } from 'react';
import { motion } from 'framer-motion';
import { Clock, CheckSquare, Percent, Bell, FileWarning } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import type { DailyAgendaItem } from '../types/chat-types';

interface DailyAgendaCardProps {
    items: DailyAgendaItem[];
}

const currencyFormatter = new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
});

const dateFormatter = new Intl.DateTimeFormat('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
});

interface AgendaGroup {
    key: string;
    label: string;
    icon: React.ReactNode;
    items: DailyAgendaItem[];
}

const groupConfig: Record<DailyAgendaItem['type'], { label: string; icon: React.ReactNode; order: number }> = {
    overdue: {
        label: 'Überfällige Rechnungen',
        icon: <FileWarning className="h-4 w-4 text-red-500" />,
        order: 0,
    },
    deadline: {
        label: 'Fristen heute',
        icon: <Clock className="h-4 w-4 text-orange-500" />,
        order: 1,
    },
    approval: {
        label: 'Freigaben',
        icon: <CheckSquare className="h-4 w-4 text-blue-500" />,
        order: 2,
    },
    skonto: {
        label: 'Skonto-Möglichkeiten',
        icon: <Percent className="h-4 w-4 text-green-500" />,
        order: 3,
    },
    reminder: {
        label: 'Erinnerungen',
        icon: <Bell className="h-4 w-4 text-muted-foreground" />,
        order: 4,
    },
};

const priorityStyles: Record<DailyAgendaItem['priority'], string> = {
    critical: 'border-l-red-500 bg-red-50 dark:bg-red-950/20',
    high: 'border-l-orange-500 bg-orange-50 dark:bg-orange-950/20',
    medium: 'border-l-yellow-500 bg-yellow-50 dark:bg-yellow-950/20',
    low: 'border-l-border',
};

const priorityBadgeVariant: Record<DailyAgendaItem['priority'], 'destructive' | 'default' | 'secondary' | 'outline'> = {
    critical: 'destructive',
    high: 'default',
    medium: 'secondary',
    low: 'outline',
};

function formatDaysRemaining(days: number | undefined): string {
    if (days === undefined) return '';
    if (days < 0) return `${Math.abs(days)} Tage überfällig`;
    if (days === 0) return 'Heute';
    if (days === 1) return 'Morgen';
    return `${days} Tage`;
}

export const DailyAgendaCard = memo(function DailyAgendaCard({
    items,
}: DailyAgendaCardProps) {
    const groups = useMemo(() => {
        const groupMap = new Map<DailyAgendaItem['type'], DailyAgendaItem[]>();

        for (const item of items) {
            const existing = groupMap.get(item.type) || [];
            existing.push(item);
            groupMap.set(item.type, existing);
        }

        const result: AgendaGroup[] = [];
        for (const [type, groupItems] of groupMap) {
            const config = groupConfig[type];
            result.push({
                key: type,
                label: config.label,
                icon: config.icon,
                items: groupItems,
            });
        }

        result.sort((a, b) => {
            const orderA = groupConfig[a.key as DailyAgendaItem['type']].order;
            const orderB = groupConfig[b.key as DailyAgendaItem['type']].order;
            return orderA - orderB;
        });

        return result;
    }, [items]);

    return (
        <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
        >
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="text-sm flex items-center gap-2">
                        <Clock className="h-4 w-4" />
                        Tagesplanung
                        <Badge variant="secondary" className="ml-auto">
                            {items.length} {items.length === 1 ? 'Eintrag' : 'Einträge'}
                        </Badge>
                    </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                    {groups.map((group) => (
                        <div key={group.key} className="space-y-2">
                            <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground uppercase tracking-wide">
                                {group.icon}
                                {group.label}
                                <span className="text-muted-foreground/60">({group.items.length})</span>
                            </div>
                            <div className="space-y-1.5">
                                {group.items.map((item, index) => (
                                    <motion.div
                                        key={item.id}
                                        initial={{ opacity: 0, x: -8 }}
                                        animate={{ opacity: 1, x: 0 }}
                                        transition={{ duration: 0.2, delay: index * 0.05 }}
                                        className={cn(
                                            'flex items-center justify-between p-2.5 rounded-md border-l-4 text-sm',
                                            priorityStyles[item.priority]
                                        )}
                                    >
                                        <div className="flex flex-col gap-0.5 min-w-0">
                                            <span className="font-medium truncate">{item.title}</span>
                                            {item.entity_name && (
                                                <span className="text-xs text-muted-foreground truncate">
                                                    {item.entity_name}
                                                </span>
                                            )}
                                        </div>
                                        <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                                            {item.amount !== undefined && (
                                                <span className="text-xs font-mono">
                                                    {currencyFormatter.format(item.amount)}
                                                </span>
                                            )}
                                            <Badge variant={priorityBadgeVariant[item.priority]} className="text-[10px] px-1.5">
                                                {item.days_remaining !== undefined
                                                    ? formatDaysRemaining(item.days_remaining)
                                                    : dateFormatter.format(new Date(item.due_date))}
                                            </Badge>
                                        </div>
                                    </motion.div>
                                ))}
                            </div>
                        </div>
                    ))}
                </CardContent>
            </Card>
        </motion.div>
    );
});

export default DailyAgendaCard;
