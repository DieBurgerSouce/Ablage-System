/**
 * CompanyComparisonCard Component
 *
 * Zeigt zusammenfassende Statistiken für die Cross-Company Übersicht.
 * Drei Karten: Beide Firmen, Nur Folie, Nur Messer
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Building2, Factory, Layers } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { CrossCompanySummary } from '../api/relationships-api';

interface CompanyComparisonCardProps {
    summary: CrossCompanySummary;
    className?: string;
}

interface StatCardProps {
    title: string;
    value: number;
    description: string;
    icon: React.ReactNode;
    variant: 'both' | 'folie' | 'messer';
    isActive?: boolean;
    onClick?: () => void;
}

function StatCard({ title, value, description, icon, variant, isActive, onClick }: StatCardProps) {
    const variantStyles = {
        both: {
            bg: 'bg-gradient-to-br from-emerald-50 to-teal-50 dark:from-emerald-950/30 dark:to-teal-950/30',
            border: 'border-emerald-200 dark:border-emerald-800',
            text: 'text-emerald-700 dark:text-emerald-300',
            iconBg: 'bg-emerald-100 dark:bg-emerald-900',
        },
        folie: {
            bg: 'bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-950/30 dark:to-indigo-950/30',
            border: 'border-blue-200 dark:border-blue-800',
            text: 'text-blue-700 dark:text-blue-300',
            iconBg: 'bg-blue-100 dark:bg-blue-900',
        },
        messer: {
            bg: 'bg-gradient-to-br from-amber-50 to-orange-50 dark:from-amber-950/30 dark:to-orange-950/30',
            border: 'border-amber-200 dark:border-amber-800',
            text: 'text-amber-700 dark:text-amber-300',
            iconBg: 'bg-amber-100 dark:bg-amber-900',
        },
    };

    const styles = variantStyles[variant];

    return (
        <Card
            className={cn(
                'transition-all duration-200 cursor-pointer hover:shadow-md',
                styles.bg,
                styles.border,
                isActive && 'ring-2 ring-primary ring-offset-2'
            )}
            onClick={onClick}
        >
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                    {title}
                </CardTitle>
                <div className={cn('p-2 rounded-lg', styles.iconBg, styles.text)}>
                    {icon}
                </div>
            </CardHeader>
            <CardContent>
                <div className={cn('text-3xl font-bold', styles.text)}>{value}</div>
                <p className="text-xs text-muted-foreground mt-1">{description}</p>
            </CardContent>
        </Card>
    );
}

/**
 * Grid mit drei Vergleichskarten für die Firmen-Übersicht.
 */
export function CompanyComparisonCard({
    summary,
    className,
}: CompanyComparisonCardProps) {
    return (
        <div className={cn('grid gap-4 md:grid-cols-3', className)}>
            <StatCard
                title="Beide Firmen"
                value={summary.multiCompanyCount}
                description="Geschäftspartner in Folie UND Messer"
                icon={<Layers className="h-5 w-5" />}
                variant="both"
            />
            <StatCard
                title="Nur Folie"
                value={summary.folieOnlyCount}
                description="Ausschließlich in Spargelfolie"
                icon={<Building2 className="h-5 w-5" />}
                variant="folie"
            />
            <StatCard
                title="Nur Messer"
                value={summary.messerOnlyCount}
                description="Ausschließlich in Spargelmesser"
                icon={<Factory className="h-5 w-5" />}
                variant="messer"
            />
        </div>
    );
}

export default CompanyComparisonCard;
