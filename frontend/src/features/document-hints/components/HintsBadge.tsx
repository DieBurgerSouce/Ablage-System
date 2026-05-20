import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { AlertCircle, AlertTriangle, Info } from 'lucide-react';
import { type DocumentHintSchema } from '../api/document-hints-api';

interface HintsBadgeProps {
    hints: DocumentHintSchema[];
    className?: string;
}

export function HintsBadge({ hints, className }: HintsBadgeProps) {
    if (!hints || hints.length === 0) {
        return null;
    }

    const criticalCount = hints.filter((h) => h.severity === 'critical').length;
    const warningCount = hints.filter((h) => h.severity === 'warning').length;
    const infoCount = hints.filter((h) => h.severity === 'info').length;

    let variant: 'destructive' | 'warning' | 'secondary' = 'secondary';
    let Icon = Info;
    let tooltipText = `${infoCount} Info-Hinweise`;

    if (criticalCount > 0) {
        variant = 'destructive';
        Icon = AlertCircle;
        tooltipText = `${criticalCount} kritische Hinweise`;
    } else if (warningCount > 0) {
        variant = 'warning';
        Icon = AlertTriangle;
        tooltipText = `${warningCount} Warnungen`;
    }

    return (
        <TooltipProvider>
            <Tooltip>
                <TooltipTrigger asChild>
                    <Badge
                        variant={variant}
                        className={`flex items-center gap-1 ${className || ''}`}
                    >
                        <Icon className="h-3 w-3" />
                        <span>{hints.length}</span>
                    </Badge>
                </TooltipTrigger>
                <TooltipContent>
                    <div className="text-sm">
                        <p className="font-semibold mb-1">{tooltipText}</p>
                        {criticalCount > 0 && <p className="text-red-500">{criticalCount} Kritisch</p>}
                        {warningCount > 0 && <p className="text-yellow-500">{warningCount} Warnung</p>}
                        {infoCount > 0 && <p className="text-blue-500">{infoCount} Info</p>}
                    </div>
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    );
}
