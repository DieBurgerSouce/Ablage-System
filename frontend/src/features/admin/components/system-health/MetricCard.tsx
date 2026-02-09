import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';

interface MetricCardProps {
    icon: React.ReactNode;
    title: string;
    value: string;
    unit?: string;
    percentage: number;
    subtitle?: string;
    className?: string;
}

function getProgressColor(percentage: number): string {
    if (percentage >= 85) return 'bg-red-500';
    if (percentage >= 60) return 'bg-yellow-500';
    return 'bg-green-500';
}

function getTextColor(percentage: number): string {
    if (percentage >= 85) return 'text-red-600';
    if (percentage >= 60) return 'text-yellow-600';
    return 'text-green-600';
}

export function MetricCard({
    icon,
    title,
    value,
    unit,
    percentage,
    subtitle,
    className,
}: MetricCardProps) {
    const safePercentage = Math.min(100, Math.max(0, percentage));

    return (
        <Card className={cn('', className)}>
            <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                    {icon}
                    {title}
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
                <div className="flex items-baseline gap-1">
                    <span className={cn('text-2xl font-bold', getTextColor(safePercentage))}>
                        {value}
                    </span>
                    {unit && (
                        <span className="text-sm text-muted-foreground">{unit}</span>
                    )}
                </div>
                <Progress
                    value={safePercentage}
                    className="h-2"
                    indicatorClassName={getProgressColor(safePercentage)}
                    aria-label={`${title}: ${safePercentage.toFixed(0)}%`}
                />
                {subtitle && (
                    <p className="text-xs text-muted-foreground">{subtitle}</p>
                )}
            </CardContent>
        </Card>
    );
}
