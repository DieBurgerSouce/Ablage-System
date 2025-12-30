import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { AlertCircle, RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Link } from '@tanstack/react-router'

export function DashboardSectionError({
    section,
    onRetry
}: {
    section: string
    onRetry?: () => void
}) {
    return (
        <Card className="border-destructive/50 bg-destructive/5">
            <CardContent className="p-6 text-center">
                <AlertCircle className="h-8 w-8 text-destructive mx-auto mb-3" aria-hidden="true" />
                <p className="font-medium text-destructive mb-1">
                    {section} konnte nicht geladen werden
                </p>
                <p className="text-sm text-muted-foreground mb-4">
                    Bitte versuchen Sie es erneut oder kontaktieren Sie den Support.
                </p>
                {onRetry ? (
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={onRetry}
                        aria-label={`${section} erneut laden`}
                    >
                        <RefreshCw className="w-4 h-4 mr-2" aria-hidden="true" />
                        Erneut versuchen
                    </Button>
                ) : (
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => window.location.reload()}
                        aria-label="Seite neu laden"
                    >
                        <RefreshCw className="w-4 h-4 mr-2" aria-hidden="true" />
                        Seite neu laden
                    </Button>
                )}
            </CardContent>
        </Card>
    )
}

export function QueryErrorAlert({
    title,
    error,
    onRetry
}: {
    title: string
    error: Error | null
    onRetry?: () => void
}) {
    return (
        <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" aria-hidden="true" />
            <AlertTitle>{title}</AlertTitle>
            <AlertDescription className="flex items-center justify-between">
                <span>{error?.message || 'Verbindung zum Server fehlgeschlagen'}</span>
                {onRetry && (
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={onRetry}
                        className="ml-2"
                        aria-label={`${title} erneut laden`}
                    >
                        <RefreshCw className="w-3 h-3 mr-1" aria-hidden="true" />
                        Wiederholen
                    </Button>
                )}
            </AlertDescription>
        </Alert>
    )
}

interface KPICardProps {
    title: string
    value: number
    icon: React.ComponentType<{ className?: string }>
    trend: 'up' | 'neutral' | 'positive' | 'warning'
    subtext?: string
    href: string
    isCurrency?: boolean
    isPercent?: boolean
}

export function KPICard({ title, value, icon: Icon, trend, subtext, href, isCurrency = true, isPercent = false }: KPICardProps) {
    const trendColors = {
        up: 'text-green-600',
        neutral: 'text-muted-foreground',
        positive: 'text-green-600',
        warning: 'text-amber-600',
    }

    const formatValue = (val: number) => {
        if (isPercent) {
            return `${val.toFixed(1)}%`
        }
        if (isCurrency) {
            return new Intl.NumberFormat('de-DE', {
                style: 'currency',
                currency: 'EUR',
            }).format(val)
        }
        return val.toLocaleString('de-DE')
    }

    return (
        <Link to={href}>
            <Card className="hover:shadow-lg transition-all hover:border-primary/50 cursor-pointer h-full">
                <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                        <CardDescription>{title}</CardDescription>
                        <Icon className={cn('w-5 h-5', trendColors[trend])} />
                    </div>
                </CardHeader>
                <CardContent>
                    <p className="text-2xl font-bold">{formatValue(value)}</p>
                    {subtext && (
                        <p className="text-xs text-muted-foreground mt-1">{subtext}</p>
                    )}
                </CardContent>
            </Card>
        </Link>
    )
}
