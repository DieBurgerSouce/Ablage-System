/**
 * TimelineEvent Component
 *
 * Einzelnes Event in der Entity-Timeline.
 * Zeigt Event-Typ, Titel, Beschreibung und Timestamp.
 */

import {
    FileText,
    Receipt,
    Truck,
    FileCheck,
    Banknote,
    File,
    PlusCircle,
    Edit,
    LucideIcon,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { TimelineEvent as TimelineEventType } from '../api/relationships-api';

// ==================== Types ====================

interface TimelineEventProps {
    event: TimelineEventType;
    isLast?: boolean;
    onClick?: () => void;
}

// ==================== Icon Mapping ====================

const ICON_MAP: Record<string, LucideIcon> = {
    'file-text': FileText,
    'receipt': Receipt,
    'truck': Truck,
    'file-check': FileCheck,
    'banknote': Banknote,
    'file': File,
    'plus-circle': PlusCircle,
    'edit': Edit,
};

// ==================== Event Type Styles ====================

const EVENT_STYLES: Record<string, {
    bgColor: string;
    borderColor: string;
    textColor: string;
}> = {
    document_linked: {
        bgColor: 'bg-blue-100 dark:bg-blue-900/30',
        borderColor: 'border-blue-500',
        textColor: 'text-blue-600 dark:text-blue-400',
    },
    entity_created: {
        bgColor: 'bg-green-100 dark:bg-green-900/30',
        borderColor: 'border-green-500',
        textColor: 'text-green-600 dark:text-green-400',
    },
    entity_updated: {
        bgColor: 'bg-amber-100 dark:bg-amber-900/30',
        borderColor: 'border-amber-500',
        textColor: 'text-amber-600 dark:text-amber-400',
    },
};

// ==================== Helper Functions ====================

function formatTimestamp(timestamp: string | null): string {
    if (!timestamp) return '—';
    const date = new Date(timestamp);
    return date.toLocaleDateString('de-DE', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    });
}

function formatRelativeTime(timestamp: string | null): string {
    if (!timestamp) return '';

    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return 'Heute';
    if (diffDays === 1) return 'Gestern';
    if (diffDays < 7) return `Vor ${diffDays} Tagen`;
    if (diffDays < 30) return `Vor ${Math.floor(diffDays / 7)} Wochen`;
    if (diffDays < 365) return `Vor ${Math.floor(diffDays / 30)} Monaten`;
    return `Vor ${Math.floor(diffDays / 365)} Jahren`;
}

// ==================== Component ====================

export function TimelineEvent({ event, isLast = false, onClick }: TimelineEventProps) {
    const Icon = ICON_MAP[event.icon] || File;
    const styles = EVENT_STYLES[event.eventType] || EVENT_STYLES.document_linked;
    const hasDocument = event.metadata?.documentId;
    const isClickable = hasDocument && onClick;

    return (
        <div className="relative flex gap-4">
            {/* Timeline Line */}
            {!isLast && (
                <div className="absolute left-5 top-10 bottom-0 w-0.5 bg-border" />
            )}

            {/* Event Icon */}
            <div
                className={cn(
                    'relative z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border-2',
                    styles.bgColor,
                    styles.borderColor
                )}
            >
                <Icon className={cn('h-5 w-5', styles.textColor)} />
            </div>

            {/* Event Content */}
            <div
                className={cn(
                    'flex-1 pb-6',
                    isClickable && 'cursor-pointer'
                )}
                onClick={isClickable ? onClick : undefined}
            >
                <div
                    className={cn(
                        'rounded-lg border bg-card p-3 transition-colors',
                        isClickable && 'hover:border-primary/50 hover:bg-accent/50'
                    )}
                >
                    {/* Header */}
                    <div className="flex items-start justify-between gap-2">
                        <div>
                            <h4 className="font-medium text-sm">{event.title}</h4>
                            <p className="text-sm text-muted-foreground mt-0.5">
                                {event.description}
                            </p>
                        </div>
                        <div className="text-right shrink-0">
                            <p className="text-xs text-muted-foreground">
                                {formatRelativeTime(event.timestamp)}
                            </p>
                            <p className="text-[10px] text-muted-foreground/70">
                                {formatTimestamp(event.timestamp)}
                            </p>
                        </div>
                    </div>

                    {/* Metadata Pills */}
                    {event.metadata?.documentType && (
                        <div className="mt-2 flex flex-wrap gap-1">
                            <span className="inline-flex items-center rounded-md bg-muted px-2 py-0.5 text-xs">
                                {event.metadata.documentType}
                            </span>
                            {event.metadata.mimeType && (
                                <span className="inline-flex items-center rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                                    {event.metadata.mimeType}
                                </span>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

export default TimelineEvent;
