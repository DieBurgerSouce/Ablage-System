/**
 * DATEV Export Status Badge
 *
 * Zeigt den Status eines Exports als farbcodiertes Badge an.
 */

import { Badge } from '@/components/ui/badge';
import { CheckCircle2, XCircle, AlertTriangle } from 'lucide-react';
import { formatExportStatus } from '@/features/datev/utils';
import type { DATEVExportStatus } from '@/lib/api/services/datev';

interface ExportStatusBadgeProps {
    status: DATEVExportStatus;
    showIcon?: boolean;
}

export function ExportStatusBadge({ status, showIcon = true }: ExportStatusBadgeProps) {
    const label = formatExportStatus(status);

    const getIcon = () => {
        switch (status) {
            case 'completed':
                return <CheckCircle2 className="h-3 w-3 mr-1" />;
            case 'failed':
                return <XCircle className="h-3 w-3 mr-1" />;
            case 'partial':
                return <AlertTriangle className="h-3 w-3 mr-1" />;
            default:
                return null;
        }
    };

    const getClassName = () => {
        switch (status) {
            case 'completed':
                return 'bg-green-100 text-green-800 hover:bg-green-100';
            case 'failed':
                return 'bg-red-100 text-red-800 hover:bg-red-100';
            case 'partial':
                return 'bg-yellow-100 text-yellow-800 hover:bg-yellow-100';
            default:
                return '';
        }
    };

    return (
        <Badge variant="secondary" className={getClassName()}>
            {showIcon && getIcon()}
            {label}
        </Badge>
    );
}
