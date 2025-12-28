/**
 * MahnKanbanBoard - Kanban-Board für Mahnvorgänge
 *
 * Visualisiert Mahnvorgänge in Spalten nach Status:
 * - Neu (Stufe 0)
 * - Erinnerung (Stufe 1)
 * - 1. Mahnung (Stufe 2)
 * - 2. Mahnung (Stufe 3)
 * - Letzte Mahnung (Stufe 4)
 * - Inkasso (Stufe 5)
 */

import { useState, useMemo } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';
import {
    Mail,
    FileWarning,
    Phone,
    AlertTriangle,
    Gavel,
    PauseCircle,
    Building2,
    User,
    Euro,
    Calendar,
} from 'lucide-react';
import { useDunningRecords } from '../hooks/use-banking-queries';
import type { DunningRecord } from '@/types/models/banking';
import { formatCurrency, formatDate } from '../utils/format';
import { cn } from '@/lib/utils';
import { MahnungDetailSheet } from './MahnungDetailSheet';
import { TelefonProtokollDialog } from './TelefonProtokollDialog';

// ==================== Types ====================

interface KanbanColumn {
    level: number;
    title: string;
    icon: React.ReactNode;
    color: string;
    bgColor: string;
}

// ==================== Configuration ====================

const COLUMNS: KanbanColumn[] = [
    {
        level: 0,
        title: 'Neu',
        icon: <Mail className="h-4 w-4" />,
        color: 'text-gray-600',
        bgColor: 'bg-gray-50 border-gray-200',
    },
    {
        level: 1,
        title: 'Erinnerung',
        icon: <Mail className="h-4 w-4" />,
        color: 'text-blue-600',
        bgColor: 'bg-blue-50 border-blue-200',
    },
    {
        level: 2,
        title: '1. Mahnung',
        icon: <FileWarning className="h-4 w-4" />,
        color: 'text-yellow-600',
        bgColor: 'bg-yellow-50 border-yellow-200',
    },
    {
        level: 3,
        title: '2. Mahnung',
        icon: <Phone className="h-4 w-4" />,
        color: 'text-orange-600',
        bgColor: 'bg-orange-50 border-orange-200',
    },
    {
        level: 4,
        title: 'Letzte Mahnung',
        icon: <AlertTriangle className="h-4 w-4" />,
        color: 'text-red-600',
        bgColor: 'bg-red-50 border-red-200',
    },
    {
        level: 5,
        title: 'Inkasso',
        icon: <Gavel className="h-4 w-4" />,
        color: 'text-red-800',
        bgColor: 'bg-red-100 border-red-300',
    },
];

// ==================== Card Component ====================

function KanbanCard({
    dunning,
    onClick,
}: {
    dunning: DunningRecord;
    onClick: () => void;
}) {
    const daysOverdue = dunning.due_date
        ? Math.max(0, Math.floor((Date.now() - new Date(dunning.due_date).getTime()) / (1000 * 60 * 60 * 24)))
        : 0;

    return (
        <div
            role="button"
            tabIndex={0}
            aria-label={`Mahnvorgang ${dunning.invoice_number || 'ohne Nummer'}, ${dunning.debtor_name || 'unbekannter Debitor'}, ${formatCurrency(dunning.outstanding_amount ?? 0)}`}
            className={cn(
                'bg-white rounded-lg border p-3 cursor-pointer hover:shadow-md transition-shadow focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2',
                dunning.mahnstopp && 'border-orange-300 bg-orange-50/50'
            )}
            onClick={onClick}
            onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onClick();
                }
            }}
        >
            {/* Header */}
            <div className="flex items-start justify-between gap-2 mb-2">
                <div className="font-medium text-sm truncate flex-1">
                    {dunning.invoice_number || 'Ohne Nr.'}
                </div>
                <div className="flex items-center gap-1">
                    {dunning.is_b2b ? (
                        <TooltipProvider>
                            <Tooltip>
                                <TooltipTrigger>
                                    <Building2 className="h-3.5 w-3.5 text-blue-600" />
                                </TooltipTrigger>
                                <TooltipContent>B2B (11.27% Verzugszinsen)</TooltipContent>
                            </Tooltip>
                        </TooltipProvider>
                    ) : (
                        <TooltipProvider>
                            <Tooltip>
                                <TooltipTrigger>
                                    <User className="h-3.5 w-3.5 text-gray-500" />
                                </TooltipTrigger>
                                <TooltipContent>B2C (7.27% Verzugszinsen)</TooltipContent>
                            </Tooltip>
                        </TooltipProvider>
                    )}
                    {dunning.mahnstopp && (
                        <TooltipProvider>
                            <Tooltip>
                                <TooltipTrigger>
                                    <PauseCircle className="h-3.5 w-3.5 text-orange-600" />
                                </TooltipTrigger>
                                <TooltipContent>
                                    Mahnstopp: {dunning.mahnstopp_reason || 'Kein Grund'}
                                </TooltipContent>
                            </Tooltip>
                        </TooltipProvider>
                    )}
                </div>
            </div>

            {/* Debitor */}
            <div className="text-sm text-muted-foreground truncate mb-2">
                {dunning.debtor_name || '-'}
            </div>

            {/* Amount */}
            <div className="flex items-center gap-1 text-sm font-mono font-medium mb-2">
                <Euro className="h-3.5 w-3.5" />
                {formatCurrency(dunning.outstanding_amount ?? 0)}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between text-xs text-muted-foreground">
                <div className="flex items-center gap-1">
                    <Calendar className="h-3 w-3" />
                    {dunning.due_date ? formatDate(dunning.due_date) : '-'}
                </div>
                {daysOverdue > 0 && (
                    <Badge variant="destructive" className="text-xs h-5">
                        +{daysOverdue}d
                    </Badge>
                )}
            </div>

            {/* B2B Pauschale Indicator */}
            {dunning.b2b_pauschale_claimed && (
                <div className="mt-2 text-xs text-green-600 font-medium">
                    +40€ Pauschale
                </div>
            )}
        </div>
    );
}

// ==================== Column Component ====================

function KanbanColumnComponent({
    column,
    records,
    onCardClick,
}: {
    column: KanbanColumn;
    records: DunningRecord[];
    onCardClick: (dunning: DunningRecord) => void;
}) {
    const totalAmount = records.reduce((sum, r) => sum + (r.outstanding_amount ?? 0), 0);

    return (
        <div className={cn('flex flex-col min-w-[280px] max-w-[320px] border rounded-lg', column.bgColor)}>
            {/* Column Header */}
            <div className="p-3 border-b bg-white/50">
                <div className="flex items-center justify-between">
                    <div className={cn('flex items-center gap-2', column.color)}>
                        {column.icon}
                        <span className="font-medium">{column.title}</span>
                    </div>
                    <Badge variant="secondary">{records.length}</Badge>
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                    {formatCurrency(totalAmount)}
                </div>
            </div>

            {/* Cards */}
            <ScrollArea className="flex-1 p-2">
                <div className="space-y-2">
                    {records.length === 0 ? (
                        <div className="text-center text-muted-foreground text-sm py-8">
                            Keine Vorgänge
                        </div>
                    ) : (
                        records.map((dunning) => (
                            <KanbanCard
                                key={dunning.id}
                                dunning={dunning}
                                onClick={() => onCardClick(dunning)}
                            />
                        ))
                    )}
                </div>
            </ScrollArea>
        </div>
    );
}

// ==================== Main Component ====================

export function MahnKanbanBoard() {
    const [selectedDunning, setSelectedDunning] = useState<DunningRecord | null>(null);
    const [detailSheetOpen, setDetailSheetOpen] = useState(false);
    const [phoneDialogOpen, setPhoneDialogOpen] = useState(false);

    const { data: records, isLoading, isError, error, refetch } = useDunningRecords({});

    const recordsByLevel = useMemo(() => {
        const byLevel: Record<number, DunningRecord[]> = {};
        COLUMNS.forEach((col) => {
            byLevel[col.level] = [];
        });

        (records?.items ?? []).forEach((record) => {
            const level = record.dunning_level ?? 0;
            if (byLevel[level]) {
                byLevel[level].push(record);
            } else {
                byLevel[0].push(record);
            }
        });

        // Sort by days overdue within each column
        Object.values(byLevel).forEach((arr) => {
            arr.sort((a, b) => {
                const daysA = a.due_date
                    ? (Date.now() - new Date(a.due_date).getTime()) / (1000 * 60 * 60 * 24)
                    : 0;
                const daysB = b.due_date
                    ? (Date.now() - new Date(b.due_date).getTime()) / (1000 * 60 * 60 * 24)
                    : 0;
                return daysB - daysA;
            });
        });

        return byLevel;
    }, [records]);

    const handleCardClick = (dunning: DunningRecord) => {
        setSelectedDunning(dunning);
        setDetailSheetOpen(true);
    };

    const handleLogPhoneCall = () => {
        if (selectedDunning) {
            setPhoneDialogOpen(true);
        }
    };

    if (isLoading) {
        return (
            <div className="flex gap-4 overflow-x-auto pb-4">
                {COLUMNS.map((col) => (
                    <div key={col.level} className="min-w-[280px]">
                        <Skeleton className="h-[500px] w-full rounded-lg" />
                    </div>
                ))}
            </div>
        );
    }

    if (isError) {
        return (
            <Card className="border-red-200 bg-red-50/50">
                <CardContent className="py-8">
                    <div className="flex flex-col items-center justify-center space-y-4">
                        <AlertTriangle className="h-12 w-12 text-red-500" />
                        <div className="text-center">
                            <h3 className="font-semibold text-red-700">
                                Fehler beim Laden der Mahnvorgänge
                            </h3>
                            <p className="text-sm text-muted-foreground mt-1">
                                {error instanceof Error
                                    ? error.message
                                    : 'Die Mahnvorgänge konnten nicht geladen werden.'}
                            </p>
                        </div>
                        <Button
                            variant="outline"
                            onClick={() => refetch()}
                            className="border-red-300 hover:bg-red-100"
                        >
                            Erneut versuchen
                        </Button>
                    </div>
                </CardContent>
            </Card>
        );
    }

    return (
        <>
            <div className="flex gap-4 overflow-x-auto pb-4" style={{ minHeight: '600px' }}>
                {COLUMNS.map((column) => (
                    <KanbanColumnComponent
                        key={column.level}
                        column={column}
                        records={recordsByLevel[column.level] ?? []}
                        onCardClick={handleCardClick}
                    />
                ))}
            </div>

            {/* Detail Sheet */}
            <MahnungDetailSheet
                dunning={selectedDunning}
                open={detailSheetOpen}
                onOpenChange={setDetailSheetOpen}
                onLogPhoneCall={handleLogPhoneCall}
                onEscalate={() => {
                    refetch();
                    setDetailSheetOpen(false);
                }}
            />

            {/* Phone Dialog */}
            <TelefonProtokollDialog
                dunningId={selectedDunning?.id ?? ''}
                debtorName={selectedDunning?.debtor_name ?? undefined}
                open={phoneDialogOpen}
                onOpenChange={setPhoneDialogOpen}
                onSuccess={() => refetch()}
            />
        </>
    );
}
