/**
 * Payment Status Badge
 * Zeigt den Status einer Zahlungsanweisung an
 */

import { Badge } from '@/components/ui/badge';
import {
    Clock,
    CheckCircle,
    XCircle,
    Send,
    AlertCircle,
    Hourglass,
} from 'lucide-react';
import type { PaymentStatus } from '@/lib/api/services/banking';

interface PaymentStatusBadgeProps {
    status: PaymentStatus;
}

const STATUS_CONFIG: Record<PaymentStatus, {
    label: string;
    variant: 'default' | 'secondary' | 'outline' | 'destructive';
    icon: React.ComponentType<{ className?: string }>;
}> = {
    draft: {
        label: 'Entwurf',
        variant: 'outline',
        icon: Clock,
    },
    pending_approval: {
        label: 'Wartet auf Freigabe',
        variant: 'secondary',
        icon: Hourglass,
    },
    approved: {
        label: 'Freigegeben',
        variant: 'default',
        icon: CheckCircle,
    },
    pending_tan: {
        label: 'TAN erforderlich',
        variant: 'secondary',
        icon: AlertCircle,
    },
    submitted: {
        label: 'Eingereicht',
        variant: 'default',
        icon: Send,
    },
    executed: {
        label: 'Ausgeführt',
        variant: 'default',
        icon: CheckCircle,
    },
    failed: {
        label: 'Fehlgeschlagen',
        variant: 'destructive',
        icon: XCircle,
    },
    cancelled: {
        label: 'Storniert',
        variant: 'outline',
        icon: XCircle,
    },
};

export function PaymentStatusBadge({ status }: PaymentStatusBadgeProps) {
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
