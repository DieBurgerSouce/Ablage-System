/**
 * Trend Chart Component
 *
 * Responsive line chart for displaying trend data.
 */

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import type { TrendDataPoint } from '../types/executive-types'

interface TrendChartProps {
  title: string
  description?: string
  data: TrendDataPoint[]
  valueLabel: string
  format?: 'number' | 'currency' | 'percentage' | 'time'
  color?: string
}

export function TrendChart({
  title,
  description,
  data,
  valueLabel,
  format = 'number',
  color = 'hsl(var(--primary))',
}: TrendChartProps) {
  // Format value for tooltip
  const formatValue = (value: number) => {
    switch (format) {
      case 'currency':
        return new Intl.NumberFormat('de-DE', {
          style: 'currency',
          currency: 'EUR',
        }).format(value)
      case 'percentage':
        return `${(value * 100).toFixed(1)}%`
      case 'time':
        const seconds = value / 1000
        if (seconds < 1) return `${value.toFixed(0)}ms`
        return `${seconds.toFixed(1)}s`
      case 'number':
      default:
        return new Intl.NumberFormat('de-DE').format(value)
    }
  }

  // Format date for X-axis (show day and month)
  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr)
    return new Intl.DateTimeFormat('de-DE', {
      day: '2-digit',
      month: '2-digit',
    }).format(date)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart
            data={data}
            margin={{ top: 5, right: 10, left: 10, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
            <XAxis
              dataKey="date"
              tickFormatter={formatDate}
              className="text-xs"
              stroke="hsl(var(--muted-foreground))"
            />
            <YAxis
              tickFormatter={(value) => {
                if (format === 'time') {
                  const seconds = value / 1000
                  return seconds < 1 ? `${value}ms` : `${seconds.toFixed(1)}s`
                }
                return new Intl.NumberFormat('de-DE', {
                  notation: 'compact',
                  compactDisplay: 'short',
                }).format(value)
              }}
              className="text-xs"
              stroke="hsl(var(--muted-foreground))"
            />
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload || !payload.length) return null

                const data = payload[0].payload as TrendDataPoint
                return (
                  <div className="rounded-lg border bg-background p-2 shadow-sm">
                    <div className="grid grid-cols-2 gap-2">
                      <div className="flex flex-col">
                        <span className="text-[0.70rem] uppercase text-muted-foreground">
                          Datum
                        </span>
                        <span className="font-bold text-muted-foreground">
                          {new Intl.DateTimeFormat('de-DE', {
                            day: '2-digit',
                            month: 'short',
                            year: 'numeric',
                          }).format(new Date(data.date))}
                        </span>
                      </div>
                      <div className="flex flex-col">
                        <span className="text-[0.70rem] uppercase text-muted-foreground">
                          {valueLabel}
                        </span>
                        <span className="font-bold">
                          {formatValue(data.value)}
                        </span>
                      </div>
                    </div>
                  </div>
                )
              }}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke={color}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
}
