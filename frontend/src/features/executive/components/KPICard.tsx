/**
 * KPI Card Component
 *
 * Displays a single KPI with value, trend indicator, and icon.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ArrowUp, ArrowDown, Minus } from 'lucide-react'

type LucideIcon = React.ComponentType<{ className?: string }>
import { cn } from '@/lib/utils'

interface KPICardProps {
  title: string
  value: string | number
  trend?: number // Percentage, positive = up, negative = down
  icon: LucideIcon
  iconColor?: string
  format?: 'number' | 'currency' | 'percentage' | 'time'
}

export function KPICard({
  title,
  value,
  trend,
  icon: Icon,
  iconColor = 'text-primary',
  format = 'number',
}: KPICardProps) {
  // Format value based on type
  const formattedValue = (() => {
    if (typeof value === 'string') return value

    switch (format) {
      case 'currency':
        return new Intl.NumberFormat('de-DE', {
          style: 'currency',
          currency: 'EUR',
          minimumFractionDigits: 2,
        }).format(value)
      case 'percentage':
        return `${(value * 100).toFixed(1)}%`
      case 'time':
        // Convert ms to seconds
        const seconds = value / 1000
        if (seconds < 1) return `${value.toFixed(0)}ms`
        return `${seconds.toFixed(1)}s`
      case 'number':
      default:
        return new Intl.NumberFormat('de-DE').format(value)
    }
  })()

  // Determine trend indicator
  const TrendIcon = !trend ? Minus : trend > 0 ? ArrowUp : ArrowDown
  const trendColor = !trend
    ? 'text-muted-foreground'
    : trend > 0
      ? 'text-green-600 dark:text-green-500'
      : 'text-red-600 dark:text-red-500'

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
        <Icon className={cn('h-4 w-4', iconColor)} />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{formattedValue}</div>
        {trend !== undefined && (
          <div className={cn('flex items-center gap-1 text-xs font-medium mt-1', trendColor)}>
            <TrendIcon className="h-3 w-3" />
            <span>{Math.abs(trend).toFixed(1)}%</span>
            <span className="text-muted-foreground font-normal">
              vs. Vormonat
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
