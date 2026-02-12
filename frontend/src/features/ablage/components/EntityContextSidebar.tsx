import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, TrendingUp, TrendingDown, Minus, AlertTriangle, CreditCard, Bell, Lightbulb, Loader2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { RiskScoreBadge } from './RiskScoreBadge'
import { getEntityContext } from '../api/entity-context-api'
import { cn } from '@/lib/utils'

interface EntityContextSidebarProps {
  entityId: string
  entityType: 'customer' | 'supplier'
}

export function EntityContextSidebar({ entityId, entityType }: EntityContextSidebarProps) {
  const [isOpen, setIsOpen] = useState(true)

  const { data: context, isLoading, error } = useQuery({
    queryKey: ['entityContext', entityId],
    queryFn: () => getEntityContext(entityId),
    enabled: !!entityId,
    staleTime: 5 * 60 * 1000, // 5 min
  })

  const getTrendIcon = (trend: string | null) => {
    switch (trend) {
      case 'IMPROVING':
        return <TrendingUp className="w-4 h-4 text-green-600" />
      case 'WORSENING':
        return <TrendingDown className="w-4 h-4 text-red-600" />
      case 'STABLE':
        return <Minus className="w-4 h-4 text-gray-500" />
      default:
        return null
    }
  }

  const getSeverityConfig = (severity: string) => {
    switch (severity) {
      case 'CRITICAL':
        return { color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400', label: 'Kritisch' }
      case 'HIGH':
        return { color: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400', label: 'Hoch' }
      case 'MEDIUM':
        return { color: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400', label: 'Mittel' }
      case 'LOW':
        return { color: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400', label: 'Niedrig' }
      default:
        return { color: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400', label: 'Info' }
    }
  }

  return (
    <div
      className={cn(
        'relative border-l bg-background transition-all duration-300 flex-shrink-0',
        isOpen ? 'w-80' : 'w-12'
      )}
    >
      {/* Toggle Button */}
      <Button
        variant="ghost"
        size="icon"
        className="absolute -left-4 top-4 z-10 rounded-full shadow-md bg-background border"
        onClick={() => setIsOpen(!isOpen)}
        aria-label={isOpen ? 'Kontext ausblenden' : 'Kontext einblenden'}
      >
        {isOpen ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
      </Button>

      {/* Collapsed State: Vertical Text */}
      {!isOpen && (
        <div className="flex items-center justify-center h-full">
          <span className="text-xs text-muted-foreground transform -rotate-90 whitespace-nowrap">
            Kontext
          </span>
        </div>
      )}

      {/* Expanded State: Content */}
      {isOpen && (
        <div className="p-4 space-y-4 overflow-y-auto h-full">
          <h3 className="font-semibold text-lg mb-4">
            {entityType === 'customer' ? 'Kunden-Kontext' : 'Lieferanten-Kontext'}
          </h3>

          {/* Loading State */}
          {isLoading && (
            <div className="flex flex-col items-center justify-center py-8 gap-3">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Lade Kontext...</span>
            </div>
          )}

          {/* Error State */}
          {error && !isLoading && (
            <div className="text-center py-8 text-muted-foreground">
              <AlertTriangle className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">Kontext nicht verfügbar</p>
            </div>
          )}

          {/* Content */}
          {!isLoading && !error && context && (
            <>
              {/* Risk Score Card */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4" />
                    Risiko-Score
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-center justify-between">
                    <RiskScoreBadge score={context.risk_score} compact />
                    {getTrendIcon(context.risk_trend)}
                  </div>
                  {context.risk_level && (
                    <p className="text-xs text-muted-foreground">
                      Risiko-Niveau: {context.risk_level}
                    </p>
                  )}
                </CardContent>
              </Card>

              {/* Financial Card */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <CreditCard className="w-4 h-4" />
                    Finanzen
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-muted-foreground">Offene Rechnungen:</span>
                    <Badge variant={context.open_invoices > 0 ? 'destructive' : 'secondary'} className="text-xs">
                      {context.open_invoices}
                    </Badge>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-muted-foreground">Offener Betrag:</span>
                    <span className="text-sm font-semibold">
                      {context.total_outstanding.toFixed(2)}€
                    </span>
                  </div>
                  {context.avg_payment_days > 0 && (
                    <div className="flex justify-between items-center">
                      <span className="text-xs text-muted-foreground">Ø Zahlungsziel:</span>
                      <span className="text-sm">{context.avg_payment_days} Tage</span>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Recent Alerts */}
              {context.recent_alerts.length > 0 && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <Bell className="w-4 h-4" />
                      Aktuelle Warnungen
                      <Badge variant="secondary" className="text-xs ml-auto">
                        {context.recent_alerts.length}
                      </Badge>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {context.recent_alerts.slice(0, 3).map((alert) => {
                        const severityConfig = getSeverityConfig(alert.severity)
                        return (
                          <div
                            key={alert.id}
                            className="p-2 rounded-md bg-muted/50 space-y-1"
                          >
                            <Badge variant="outline" className={`${severityConfig.color} text-xs`}>
                              {severityConfig.label}
                            </Badge>
                            <p className="text-xs line-clamp-2">{alert.title}</p>
                            <p className="text-[10px] text-muted-foreground">
                              {new Date(alert.created_at).toLocaleDateString('de-DE')}
                            </p>
                          </div>
                        )
                      })}
                      {context.recent_alerts.length > 3 && (
                        <p className="text-xs text-muted-foreground text-center pt-1">
                          {context.recent_alerts.length - 3} weitere...
                        </p>
                      )}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Skonto Opportunities */}
              {(context.skonto_opportunities > 0 || context.skonto_potential_savings > 0) && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <Lightbulb className="w-4 h-4" />
                      Skonto-Chancen
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <div className="flex justify-between items-center">
                      <span className="text-xs text-muted-foreground">Verfügbare:</span>
                      <Badge variant="secondary" className="text-xs">
                        {context.skonto_opportunities}
                      </Badge>
                    </div>
                    {context.skonto_potential_savings > 0 && (
                      <div className="flex justify-between items-center">
                        <span className="text-xs text-muted-foreground">Potenzial:</span>
                        <span className="text-sm font-semibold text-green-600 dark:text-green-400">
                          {context.skonto_potential_savings.toFixed(2)}€
                        </span>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
