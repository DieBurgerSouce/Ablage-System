/**
 * Skonto Card Component
 *
 * Zeigt Skonto-Möglichkeiten als Liste mit Einsparungspotenzial an.
 */

import { memo, useMemo } from 'react';
import { motion } from 'framer-motion';
import { Percent, AlertTriangle, PiggyBank } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import type { SkontoOpportunity } from '../types/chat-types';

interface SkontoCardProps {
    items: SkontoOpportunity[];
}

const currencyFormatter = new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
});

function formatDaysRemaining(days: number): string {
    if (days < 0) return `${Math.abs(days)} Tage überfällig`;
    if (days === 0) return 'Heute';
    if (days === 1) return 'Morgen';
    return `${days} Tage`;
}

export const SkontoCard = memo(function SkontoCard({
    items,
}: SkontoCardProps) {
    const totalSavings = useMemo(
        () => items.reduce((sum, item) => sum + item.skonto_amount, 0),
        [items]
    );

    return (
        <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
        >
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="text-sm flex items-center gap-2">
                        <Percent className="h-4 w-4" />
                        Skonto-Möglichkeiten
                        <Badge variant="secondary" className="ml-auto">
                            {items.length} {items.length === 1 ? 'Rechnung' : 'Rechnungen'}
                        </Badge>
                    </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                    {items.map((item, index) => {
                        const isUrgent = item.days_remaining <= 3;

                        return (
                            <motion.div
                                key={item.document_id}
                                initial={{ opacity: 0, x: -8 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ duration: 0.2, delay: index * 0.05 }}
                                className={cn(
                                    'flex items-center justify-between p-2.5 rounded-md border text-sm',
                                    isUrgent
                                        ? 'border-red-300 dark:border-red-800 bg-red-50 dark:bg-red-950/20'
                                        : 'border-border'
                                )}
                            >
                                <div className="flex flex-col gap-0.5 min-w-0">
                                    <div className="flex items-center gap-1.5">
                                        {isUrgent && (
                                            <AlertTriangle className="h-3.5 w-3.5 text-red-500 flex-shrink-0" />
                                        )}
                                        <span className="font-medium truncate">
                                            {item.invoice_number}
                                        </span>
                                    </div>
                                    <span className="text-xs text-muted-foreground truncate">
                                        {item.entity_name}
                                    </span>
                                </div>
                                <div className="flex items-center gap-2.5 flex-shrink-0 ml-2">
                                    <div className="text-right">
                                        <div className="text-xs text-muted-foreground">
                                            {currencyFormatter.format(item.total_amount)}
                                        </div>
                                        <div className="text-xs font-medium text-green-600 dark:text-green-400">
                                            -{item.skonto_percent}% = {currencyFormatter.format(item.skonto_amount)}
                                        </div>
                                    </div>
                                    <Badge
                                        variant={isUrgent ? 'destructive' : 'outline'}
                                        className="text-[10px] px-1.5 whitespace-nowrap"
                                    >
                                        {formatDaysRemaining(item.days_remaining)}
                                    </Badge>
                                </div>
                            </motion.div>
                        );
                    })}

                    {/* Total savings row */}
                    <div className="flex items-center justify-between pt-3 mt-2 border-t">
                        <div className="flex items-center gap-2 text-sm font-medium">
                            <PiggyBank className="h-4 w-4 text-green-600 dark:text-green-400" />
                            Einsparungspotenzial
                        </div>
                        <span className="text-sm font-mono font-medium text-green-600 dark:text-green-400">
                            {currencyFormatter.format(totalSavings)}
                        </span>
                    </div>
                </CardContent>
            </Card>
        </motion.div>
    );
});

export default SkontoCard;
