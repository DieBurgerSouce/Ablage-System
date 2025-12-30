import { useQuery } from '@tanstack/react-query'
import { adminService, type ProcessingStats, type SkontoWarningsResponse } from '@/lib/api/services/admin'
import { financeService } from '@/lib/api/services/finance'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { AlertTriangle, ArrowRight, CheckCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Link } from '@tanstack/react-router'
import { Skeleton } from '@/components/ui/skeleton'

export function TodayWidget() {
    const { data: systemDashboard, isLoading: isLoadingSystem } = useQuery({
        queryKey: ['admin-system-dashboard'],
        queryFn: () => adminService.getSystemDashboard(),
        staleTime: 30000,
        retry: 1,
    })

    const { data: financeAggregations, isLoading: isLoadingFinance } = useQuery({
        queryKey: ['finance-aggregations'],
        queryFn: () => financeService.getOverallAggregations(),
        staleTime: 60000,
        retry: 1,
    })

    const { data: deadlines, isLoading: isLoadingDeadlines } = useQuery({
        queryKey: ['finance-deadlines', { daysAhead: 3 }],
        queryFn: () => financeService.getDeadlines({ daysAhead: 3 }),
        staleTime: 60000,
        retry: 1,
    })

    const { data: skontoWarnings, isLoading: isLoadingSkontos } = useQuery({
        queryKey: ['skonto-warnings'],
        queryFn: () => adminService.getSkontoWarnings(),
        staleTime: 60000,
        retry: 1,
    })

    const isLoading = isLoadingSystem || isLoadingFinance || isLoadingDeadlines || isLoadingSkontos
    const items = buildTodayItems(systemDashboard?.processing, systemDashboard?.queue, financeAggregations, deadlines, skontoWarnings)

    if (isLoading) {
        return <Skeleton className="h-48 rounded-xl" />
    }

    return (
        <section className="space-y-4">
            <h2 className="text-xl font-semibold flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-amber-500" />
                Heute wichtig
            </h2>
            <Card>
                <CardContent className="p-0 divide-y">
                    {items.length === 0 ? (
                        <div className="flex items-center justify-center p-8 text-muted-foreground">
                            <CheckCircle className="w-5 h-5 mr-2 text-green-500" />
                            Alles erledigt! Keine dringenden Aufgaben.
                        </div>
                    ) : (
                        items.map((item, i) => (
                            <div key={i} className="flex items-center justify-between p-4 hover:bg-muted/50 transition-colors">
                                <div className="flex items-center gap-3">
                                    <ItemIcon type={item.type} />
                                    <div>
                                        <p className="font-medium">{item.text}</p>
                                        {item.subtext && (
                                            <p className="text-sm text-muted-foreground">{item.subtext}</p>
                                        )}
                                    </div>
                                    {item.amount !== undefined && item.amount > 0 && (
                                        <Badge variant="secondary" className="ml-2">
                                            {formatCurrency(item.amount)}
                                        </Badge>
                                    )}
                                </div>
                                <Link to={item.href}>
                                    <Button variant="ghost" size="sm">
                                        {item.action}
                                        <ArrowRight className="w-4 h-4 ml-1" />
                                    </Button>
                                </Link>
                            </div>
                        ))
                    )}
                </CardContent>
            </Card>
        </section>
    )
}

function ItemIcon({ type }: { type: string }) {
    const classes = {
        warning: 'text-amber-500 bg-amber-500/10',
        info: 'text-blue-500 bg-blue-500/10',
        urgent: 'text-red-500 bg-red-500/10',
        task: 'text-green-500 bg-green-500/10',
    }
    return (
        <div className={cn('p-2 rounded-lg', classes[type as keyof typeof classes] || classes.info)}>
            <AlertTriangle className="w-4 h-4" />
        </div>
    )
}

function formatCurrency(value: number): string {
    return new Intl.NumberFormat('de-DE', {
        style: 'currency',
        currency: 'EUR',
    }).format(value)
}

interface TodayItem {
    type: 'warning' | 'info' | 'urgent' | 'task'
    text: string
    subtext?: string
    amount?: number
    action: string
    href: string
}

function buildTodayItems(
    stats: ProcessingStats | undefined,
    queue: { failed_today?: number; pending?: number } | undefined,
    financeAgg: { pendingDeadlines?: number; totalNachzahlung?: number } | undefined,
    deadlines: { overdueCount?: number; urgentCount?: number; items?: Array<{ documentName: string; daysUntil: number }> } | undefined,
    skontoWarnings: SkontoWarningsResponse | undefined
): TodayItem[] {
    const items: TodayItem[] = []

    if (skontoWarnings?.items && skontoWarnings.items.length > 0) {
        const firstSkonto = skontoWarnings.items[0]
        items.push({
            type: 'urgent',
            text: `Skonto läuft ab: ${firstSkonto.sender_company}`,
            subtext: firstSkonto.days_until <= 1
                ? 'morgen!'
                : `in ${firstSkonto.days_until} Tagen`,
            amount: skontoWarnings.total_savings,
            action: 'Zahlen',
            href: '/admin/banking', // Fixed href based on routeTree
        })
    }

    if (deadlines?.overdueCount && deadlines.overdueCount > 0) {
        items.push({
            type: 'urgent',
            text: `${deadlines.overdueCount} Frist${deadlines.overdueCount > 1 ? 'en' : ''} überfällig`,
            action: 'Prüfen',
            href: '/finanzen',
        })
    }

    if (deadlines?.urgentCount && deadlines.urgentCount > 0) {
        const nextDeadline = deadlines.items?.[0]
        items.push({
            type: 'warning',
            text: `${deadlines.urgentCount} Frist${deadlines.urgentCount > 1 ? 'en' : ''} in den nächsten 3 Tagen`,
            subtext: nextDeadline ? `${nextDeadline.documentName} - in ${nextDeadline.daysUntil} Tag${nextDeadline.daysUntil !== 1 ? 'en' : ''}` : undefined,
            action: 'Ansehen',
            href: '/finanzen',
        })
    }

    if (queue?.failed_today && queue.failed_today > 0) {
        items.push({
            type: 'warning',
            text: `${queue.failed_today} Verarbeitung${queue.failed_today > 1 ? 'en' : ''} fehlgeschlagen`,
            subtext: 'heute',
            action: 'Prüfen',
            href: '/admin/job-queue', // Fixed href
        })
    }

    if (queue?.pending && queue.pending > 20) {
        items.push({
            type: 'info',
            text: `${queue.pending} Dokumente in Warteschlange`,
            subtext: 'hohe Auslastung',
            action: 'Status',
            href: '/admin/job-queue', // Fixed href
        })
    }

    if (financeAgg?.totalNachzahlung && financeAgg.totalNachzahlung > 0) {
        items.push({
            type: 'task',
            text: 'Offene Nachzahlungen',
            amount: financeAgg.totalNachzahlung,
            action: 'Übersicht',
            href: '/finanzen',
        })
    }

    return items
}
