/**
 * Mobile Dashboard Component
 *
 * Optimized dashboard layout for mobile devices:
 * - Prioritized widget display (critical first)
 * - Swipe gestures for quick actions
 * - Collapsible sections
 * - PWA-optimized for offline support
 *
 * Phase 3.3 Feature 9: Mobile-First Dashboard
 */

import { useState, useMemo, useCallback } from 'react';
import { Link } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { useSwipeableRef } from '@/hooks/use-mobile-gestures';
import { cn } from '@/lib/utils';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from '@/components/ui/collapsible';
import {
    AlertTriangle,
    AlertCircle,
    ChevronDown,
    ChevronRight,
    FileText,
    TrendingUp,
    Clock,
    CheckCircle2,
    Wallet,
    Upload,
    MoreHorizontal,
    ArrowRight,
} from 'lucide-react';
import { toast } from 'sonner';

// =============================================================================
// Types
// =============================================================================

interface QuickAction {
    id: string;
    label: string;
    icon: React.ReactNode;
    href?: string;
    onClick?: () => void;
    variant?: 'default' | 'primary' | 'warning' | 'success';
}

interface CriticalItem {
    id: string;
    title: string;
    message: string;
    type: 'warning' | 'critical' | 'info';
    href?: string;
    value?: string | number;
}

interface MobileKPI {
    label: string;
    value: string | number;
    change?: number;
    trend?: 'up' | 'down' | 'neutral';
    href?: string;
}

// =============================================================================
// API Hooks
// =============================================================================

function useMobileDashboardData() {
    return useQuery({
        queryKey: ['mobile-dashboard'],
        queryFn: async () => {
            const response = await api.get('/dashboard/mobile-summary');
            return response.data;
        },
        staleTime: 2 * 60 * 1000, // 2 minutes
        refetchInterval: 5 * 60 * 1000, // Refresh every 5 minutes
    });
}

function useRecentDocuments(limit: number = 5) {
    return useQuery({
        queryKey: ['recent-documents', limit],
        queryFn: async () => {
            const response = await api.get('/documents', {
                params: { limit, sort: '-created_at' },
            });
            return response.data;
        },
        staleTime: 1 * 60 * 1000,
    });
}

// =============================================================================
// Quick Actions Component
// =============================================================================

interface QuickActionsProps {
    actions: QuickAction[];
    onSwipeLeft?: () => void;
    onSwipeRight?: () => void;
}

function QuickActions({ actions, onSwipeLeft, onSwipeRight }: QuickActionsProps) {
    const { ref, swipeState } = useSwipeableRef(
        {
            onSwipeLeft,
            onSwipeRight,
        },
        { horizontalOnly: true, threshold: 80 }
    );

    return (
        <div
            ref={ref}
            className={cn(
                'grid grid-cols-4 gap-2 p-2',
                swipeState.isActive && 'pointer-events-none'
            )}
        >
            {actions.map((action) => {
                const content = (
                    <div
                        className={cn(
                            'flex flex-col items-center justify-center',
                            'p-3 rounded-xl',
                            'min-h-[72px]',
                            'transition-all duration-150',
                            'active:scale-95',
                            action.variant === 'primary' &&
                                'bg-primary text-primary-foreground',
                            action.variant === 'warning' &&
                                'bg-orange-100 text-orange-900 dark:bg-orange-900/30 dark:text-orange-200',
                            action.variant === 'success' &&
                                'bg-green-100 text-green-900 dark:bg-green-900/30 dark:text-green-200',
                            !action.variant &&
                                'bg-muted hover:bg-muted/80'
                        )}
                    >
                        {action.icon}
                        <span className="text-xs mt-1 text-center font-medium truncate w-full">
                            {action.label}
                        </span>
                    </div>
                );

                if (action.href) {
                    return (
                        <Link key={action.id} to={action.href}>
                            {content}
                        </Link>
                    );
                }

                return (
                    <button
                        key={action.id}
                        onClick={action.onClick}
                        className="w-full"
                    >
                        {content}
                    </button>
                );
            })}
        </div>
    );
}

// =============================================================================
// Critical Items Section
// =============================================================================

interface CriticalSectionProps {
    items: CriticalItem[];
    isLoading?: boolean;
}

function CriticalSection({ items, isLoading }: CriticalSectionProps) {
    const [isOpen, setIsOpen] = useState(true);

    if (isLoading) {
        return (
            <div className="space-y-2 p-4">
                <Skeleton className="h-20 w-full rounded-lg" />
                <Skeleton className="h-20 w-full rounded-lg" />
            </div>
        );
    }

    if (items.length === 0) {
        return (
            <div className="p-4">
                <Alert className="bg-green-50 dark:bg-green-950 border-green-200 dark:border-green-800">
                    <CheckCircle2 className="h-4 w-4 text-green-600" />
                    <AlertTitle className="text-green-800 dark:text-green-200">
                        Alles in Ordnung
                    </AlertTitle>
                    <AlertDescription className="text-green-600 dark:text-green-400">
                        Keine dringenden Aufgaben vorhanden.
                    </AlertDescription>
                </Alert>
            </div>
        );
    }

    return (
        <Collapsible open={isOpen} onOpenChange={setIsOpen}>
            <CollapsibleTrigger asChild>
                <button className="flex items-center justify-between w-full px-4 py-2 text-left">
                    <div className="flex items-center gap-2">
                        <AlertTriangle className="h-4 w-4 text-orange-500" />
                        <span className="font-semibold">Handlungsbedarf</span>
                        <Badge variant="destructive" className="text-xs">
                            {items.length}
                        </Badge>
                    </div>
                    {isOpen ? (
                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                    ) : (
                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                    )}
                </button>
            </CollapsibleTrigger>
            <CollapsibleContent>
                <div className="space-y-2 px-4 pb-4">
                    {items.map((item) => (
                        <Link
                            key={item.id}
                            to={item.href || '#'}
                            className={cn(
                                'flex items-start gap-3 p-3 rounded-lg',
                                'transition-colors',
                                item.type === 'critical'
                                    ? 'bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-800'
                                    : item.type === 'warning'
                                    ? 'bg-orange-50 dark:bg-orange-950/50 border border-orange-200 dark:border-orange-800'
                                    : 'bg-muted'
                            )}
                        >
                            <AlertCircle
                                className={cn(
                                    'h-5 w-5 mt-0.5 shrink-0',
                                    item.type === 'critical'
                                        ? 'text-red-600'
                                        : item.type === 'warning'
                                        ? 'text-orange-600'
                                        : 'text-blue-600'
                                )}
                            />
                            <div className="flex-1 min-w-0">
                                <p className="font-medium text-sm truncate">
                                    {item.title}
                                </p>
                                <p className="text-xs text-muted-foreground line-clamp-2">
                                    {item.message}
                                </p>
                            </div>
                            {item.value && (
                                <span className="text-sm font-semibold shrink-0">
                                    {item.value}
                                </span>
                            )}
                        </Link>
                    ))}
                </div>
            </CollapsibleContent>
        </Collapsible>
    );
}

// =============================================================================
// KPI Cards Component
// =============================================================================

interface KPICardsProps {
    kpis: MobileKPI[];
    isLoading?: boolean;
}

function KPICards({ kpis, isLoading }: KPICardsProps) {
    if (isLoading) {
        return (
            <div className="grid grid-cols-2 gap-2 p-4">
                {[1, 2, 3, 4].map((i) => (
                    <Skeleton key={i} className="h-20 rounded-lg" />
                ))}
            </div>
        );
    }

    return (
        <div className="grid grid-cols-2 gap-2 p-4">
            {kpis.map((kpi, index) => (
                <Link
                    key={index}
                    to={kpi.href || '#'}
                    className="block"
                >
                    <Card className="hover:bg-accent/50 transition-colors">
                        <CardContent className="p-3">
                            <p className="text-xs text-muted-foreground truncate">
                                {kpi.label}
                            </p>
                            <div className="flex items-baseline gap-2 mt-1">
                                <span className="text-xl font-bold">
                                    {kpi.value}
                                </span>
                                {kpi.change !== undefined && (
                                    <span
                                        className={cn(
                                            'text-xs font-medium',
                                            kpi.trend === 'up' && 'text-green-600',
                                            kpi.trend === 'down' && 'text-red-600'
                                        )}
                                    >
                                        {kpi.change > 0 ? '+' : ''}
                                        {kpi.change}%
                                    </span>
                                )}
                            </div>
                        </CardContent>
                    </Card>
                </Link>
            ))}
        </div>
    );
}

// =============================================================================
// Recent Documents Section
// =============================================================================

interface RecentDocumentsSectionProps {
    isLoading?: boolean;
    documents?: Array<{
        id: string;
        name: string;
        document_type?: string;
        created_at: string;
        ocr_status?: string;
    }>;
}

function RecentDocumentsSection({ documents, isLoading }: RecentDocumentsSectionProps) {
    const [isOpen, setIsOpen] = useState(true);

    if (isLoading) {
        return (
            <div className="space-y-2 p-4">
                {[1, 2, 3].map((i) => (
                    <Skeleton key={i} className="h-14 rounded-lg" />
                ))}
            </div>
        );
    }

    if (!documents || documents.length === 0) {
        return (
            <div className="p-4 text-center text-muted-foreground">
                <FileText className="h-8 w-8 mx-auto mb-2 opacity-50" />
                <p className="text-sm">Noch keine Dokumente</p>
            </div>
        );
    }

    return (
        <Collapsible open={isOpen} onOpenChange={setIsOpen}>
            <CollapsibleTrigger asChild>
                <button className="flex items-center justify-between w-full px-4 py-2 text-left">
                    <div className="flex items-center gap-2">
                        <Clock className="h-4 w-4 text-muted-foreground" />
                        <span className="font-semibold">Zuletzt hinzugefügt</span>
                    </div>
                    {isOpen ? (
                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                    ) : (
                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                    )}
                </button>
            </CollapsibleTrigger>
            <CollapsibleContent>
                <div className="space-y-1 px-4 pb-4">
                    {documents.map((doc) => (
                        <Link
                            key={doc.id}
                            to="/documents/$documentId"
                            params={{ documentId: doc.id }}
                            className="flex items-center gap-3 p-2 rounded-lg hover:bg-muted transition-colors"
                        >
                            <FileText className="h-5 w-5 text-muted-foreground shrink-0" />
                            <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium truncate">
                                    {doc.name}
                                </p>
                                <p className="text-xs text-muted-foreground">
                                    {doc.document_type || 'Dokument'}
                                </p>
                            </div>
                            {doc.ocr_status === 'processing' && (
                                <Badge variant="secondary" className="text-xs shrink-0">
                                    OCR...
                                </Badge>
                            )}
                            <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
                        </Link>
                    ))}

                    <Link
                        to="/kunden"
                        className="flex items-center justify-center gap-2 p-2 text-sm text-primary hover:underline"
                    >
                        Alle Dokumente anzeigen
                        <ArrowRight className="h-4 w-4" />
                    </Link>
                </div>
            </CollapsibleContent>
        </Collapsible>
    );
}

// =============================================================================
// Main Mobile Dashboard Component
// =============================================================================

export function MobileDashboard() {
    const { data: dashboardData, isLoading: dashboardLoading, error } = useMobileDashboardData();
    const { data: recentDocs, isLoading: docsLoading } = useRecentDocuments(5);

    // Quick actions
    const quickActions: QuickAction[] = useMemo(
        () => [
            {
                id: 'upload',
                label: 'Upload',
                icon: <Upload className="h-6 w-6" />,
                href: '/upload',
                variant: 'primary',
            },
            {
                id: 'search',
                label: 'Suche',
                icon: <FileText className="h-6 w-6" />,
                href: '/search',
            },
            {
                id: 'invoices',
                label: 'Rechnungen',
                icon: <Wallet className="h-6 w-6" />,
                href: '/invoices',
            },
            {
                id: 'more',
                label: 'Mehr',
                icon: <MoreHorizontal className="h-6 w-6" />,
                href: '/dashboard',
            },
        ],
        []
    );

    // Mock KPIs (would come from API in real implementation)
    const kpis: MobileKPI[] = useMemo(
        () =>
            dashboardData?.kpis || [
                { label: 'Offene Rechnungen', value: '12', change: -5, trend: 'down', href: '/invoices?status=open' },
                { label: 'Skonto-Chancen', value: '3', trend: 'neutral', href: '/invoices?skonto=available' },
                { label: 'Dokumente heute', value: '24', change: 12, trend: 'up', href: '/ablage' },
                { label: 'Ausstehend', value: '5.234 EUR', href: '/invoices' },
            ],
        [dashboardData]
    );

    // Mock critical items (would come from API)
    const criticalItems: CriticalItem[] = useMemo(
        () =>
            dashboardData?.criticalItems || [
                {
                    id: '1',
                    title: 'Skonto läuft ab',
                    message: 'Rechnung #INV-2024-0123 - Skonto bis morgen',
                    type: 'warning',
                    value: '54 EUR',
                    href: '/invoices/123',
                },
                {
                    id: '2',
                    title: 'Mahnung fällig',
                    message: 'Kunde Meier GmbH - Stufe 2',
                    type: 'critical',
                    value: '1.250 EUR',
                    href: '/dunning/456',
                },
            ],
        [dashboardData]
    );

    // Swipe handlers
    const handleSwipeLeft = useCallback(() => {
        toast.info('Wischen Sie nach rechts für weitere Optionen');
    }, []);

    const handleSwipeRight = useCallback(() => {
        toast.info('Wischen Sie nach links für weitere Optionen');
    }, []);

    if (error) {
        return (
            <div className="p-4">
                <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertTitle>Fehler beim Laden</AlertTitle>
                    <AlertDescription>
                        Das Dashboard konnte nicht geladen werden. Bitte versuchen Sie es erneut.
                    </AlertDescription>
                </Alert>
            </div>
        );
    }

    return (
        <div className="flex flex-col min-h-screen bg-background">
            {/* Header */}
            <header className="sticky top-0 z-40 bg-background/95 backdrop-blur border-b">
                <div className="flex items-center justify-between px-4 h-14">
                    <h1 className="text-lg font-semibold">Dashboard</h1>
                    <Link to="/alerts">
                        <Button variant="ghost" size="icon" className="relative">
                            <TrendingUp className="h-5 w-5" />
                            <span className="sr-only">Benachrichtigungen</span>
                        </Button>
                    </Link>
                </div>
            </header>

            {/* Main Content */}
            <main className="flex-1 pb-20">
                {/* Quick Actions */}
                <section aria-label="Schnellaktionen">
                    <QuickActions
                        actions={quickActions}
                        onSwipeLeft={handleSwipeLeft}
                        onSwipeRight={handleSwipeRight}
                    />
                </section>

                {/* KPI Cards */}
                <section aria-label="Kennzahlen">
                    <KPICards kpis={kpis} isLoading={dashboardLoading} />
                </section>

                {/* Divider */}
                <div className="h-2 bg-muted" />

                {/* Critical Items */}
                <section aria-label="Handlungsbedarf">
                    <CriticalSection items={criticalItems} isLoading={dashboardLoading} />
                </section>

                {/* Divider */}
                <div className="h-2 bg-muted" />

                {/* Recent Documents */}
                <section aria-label="Zuletzt hinzugefügt">
                    <RecentDocumentsSection
                        documents={recentDocs?.items}
                        isLoading={docsLoading}
                    />
                </section>
            </main>
        </div>
    );
}

export default MobileDashboard;
