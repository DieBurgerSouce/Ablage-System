/**
 * Transaction Status Badge
 * Zeigt den Reconciliation-Status einer Transaktion an
 */

import { Badge } from '@/components/ui/badge';
import { CheckCircle, Circle, CircleDot, Hand, EyeOff } from 'lucide-react';
import type { ReconciliationStatus } from '@/lib/api/services/banking';

interface TransactionStatusBadgeProps {
    status: ReconciliationStatus;
}

const STATUS_CONFIG: Record<ReconciliationStatus, {
    label: string;
    variant: 'default' | 'secondary' | 'outline' | 'destructive';
    icon: React.ComponentType<{ className?: string }>;
}> = {
    unmatched: {
        label: 'Unabgeglichen',
        variant: 'outline',
        icon: Circle,
    },
    matched: {
        label: 'Abgeglichen',
        variant: 'default',
        icon: CheckCircle,
    },
    partial: {
        label: 'Teilweise',
        variant: 'secondary',
        icon: CircleDot,
    },
    manual: {
        label: 'Manuell',
        variant: 'secondary',
        icon: Hand,
    },
    ignored: {
        label: 'Ignoriert',
        variant: 'outline',
        icon: EyeOff,
    },
};

export function TransactionStatusBadge({ status }: TransactionStatusBadgeProps) {
    const config = STATUS_CONFIG[status];

    if (!config) {
        return <Badge variant="outline">{status}</Badge>;
    }

    const Icon = config.icon;

    return (
        <Badge variant={config.variant} className="gap-1">
            <Icon className="h-3 w-3" />
            {config.label}
        </Badge>
    );
}
