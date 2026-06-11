/**
 * Command Center - Konsolidierte Startseite.
 *
 * Vereinigt KPIs, priorisierte Aufgaben, proaktive Insights,
 * Alerts und KI-Status in einer Ansicht.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { AlertTriangle, ArrowRight, Bot, CheckCircle2, ChevronRight, Clock, Database, FileText, Info, Send, TrendingDown, TrendingUp, Upload, Zap } from 'lucide-react'

import { apiClient } from '@/lib/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Progress } from '@/components/ui/progress'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

// ============================================================================
// Types (spiegeln Backend Pydantic Models)
// ============================================================================

interface KPIWidget {
  id: string
  label: string
  value: string
  raw_value: number
  unit: string
  trend: 'up' | 'down' | 'stable' | null
  trend_value: string | null
  variant: 'default' | 'success' | 'warning' | 'danger'
  icon: string | null
}

interface TaskItem {
  id: string
  title: string
  description: string | null
  priority: number
  action_type: string
  category: string
  due_date: string | null
  financial_impact: number | null
  action_route: string | null
}

interface ProactiveInsight {
  id: string
  severity: 'info' | 'warning' | 'critical'
  title: string
  description: string
  category: string
  action_label: string | null
  action_route: string | null
  created_at: string
}

interface AlertItem {
  id: string
  severity: string
  title: string
  source: string
  created_at: string
}

interface CommandCenterProgress {
  completed: number
  total: number
  percentage: number
}

interface CommandCenterResponse {
  kpis: KPIWidget[]
  tasks: TaskItem[]
  task_progress: CommandCenterProgress
  insights: ProactiveInsight[]
  alerts: AlertItem[]
  alert_count: number
  generated_at: string
  ai_status: 'operational' | 'degraded' | 'offline'
}

// ============================================================================
// Icon Mapping
// ============================================================================

const ICON_MAP: Record<string, React.ReactNode> = {
  FileText: <FileText className="h-4 w-4" />,
  Upload: <Upload className="h-4 w-4" />,
  Database: <Database className="h-4 w-4" />,
  Zap: <Zap className="h-4 w-4" />,
}

const SEVERITY_STYLES = {
  info: 'border-blue-200 bg-blue-50 dark:bg-blue-950/20 dark:border-blue-800',
  warning: 'border-amber-200 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-800',
  critical: 'border-red-200 bg-red-50 dark:bg-red-950/20 dark:border-red-800',
} as const

const SEVERITY_BADGE = {
  info: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  warning: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200',
  critical: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
} as const

const VARIANT_STYLES = {
  default: '',
  success: 'border-green-200 dark:border-green-800',
  warning: 'border-amber-200 dark:border-amber-800',
  danger: 'border-red-200 dark:border-red-800',
} as const

const PRIORITY_LABELS: Record<number, { label: string; color: string }> = {
  1: { label: 'Kritisch', color: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200' },
  2: { label: 'Hoch', color: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200' },
  3: { label: 'Mittel', color: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200' },
  4: { label: 'Normal', color: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200' },
  5: { label: 'Niedrig', color: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200' },
}

// ============================================================================
// Sub-Components
// ============================================================================

function KPICardItem({ kpi }: { kpi: KPIWidget }) {
  const icon = kpi.icon ? ICON_MAP[kpi.icon] ?? null : null

  return (
    <Card className={cn('transition-all', VARIANT_STYLES[kpi.variant] ?? '')}>
      <CardContent className="pt-4 pb-3">
        <div className="flex items-center justify-between mb-1">
          <span className="text-sm text-muted-foreground flex items-center gap-1.5">
            {icon}
            {kpi.label}
          </span>
          {kpi.trend && (
            <span className={cn(
              'flex items-center text-xs font-medium',
              kpi.trend === 'up' && 'text-green-600',
              kpi.trend === 'down' && 'text-red-600',
              kpi.trend === 'stable' && 'text-muted-foreground',
            )}>
              {kpi.trend === 'up' && <TrendingUp className="h-3 w-3 mr-0.5" />}
              {kpi.trend === 'down' && <TrendingDown className="h-3 w-3 mr-0.5" />}
              {kpi.trend_value}
            </span>
          )}
        </div>
        <div className="text-2xl font-bold">{kpi.value}</div>
        {kpi.unit && (
          <span className="text-xs text-muted-foreground">{kpi.unit}</span>
        )}
      </CardContent>
    </Card>
  )
}

function TaskListItem({ task }: { task: TaskItem }) {
  const navigate = useNavigate()
  const priority = PRIORITY_LABELS[task.priority] ?? PRIORITY_LABELS[3]

  return (
    <div
      className="flex items-center justify-between py-2.5 px-3 rounded-md hover:bg-muted/50 transition-colors cursor-pointer group"
      onClick={() => {
        if (task.action_route) {
          navigate({ to: task.action_route })
        }
      }}
    >
      <div className="flex items-center gap-3 min-w-0 flex-1">
        <Badge variant="outline" className={cn('text-[10px] shrink-0', priority.color)}>
          {priority.label}
        </Badge>
        <div className="min-w-0">
          <p className="text-sm font-medium truncate">{task.title}</p>
          {task.description && (
            <p className="text-xs text-muted-foreground truncate">{task.description}</p>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0 ml-2">
        {task.financial_impact != null && task.financial_impact > 0 && (
          <span className="text-xs font-medium text-muted-foreground">
            {task.financial_impact.toLocaleString('de-DE', {
              style: 'currency',
              currency: 'EUR',
              maximumFractionDigits: 0,
            })}
          </span>
        )}
        {task.due_date && (
          <span className="text-xs text-muted-foreground flex items-center gap-0.5">
            <Clock className="h-3 w-3" />
            {new Date(task.due_date).toLocaleDateString('de-DE', {
              day: '2-digit',
              month: '2-digit',
            })}
          </span>
        )}
        <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>
    </div>
  )
}

function InsightCard({ insight }: { insight: ProactiveInsight }) {
  const navigate = useNavigate()
  const severity = insight.severity as keyof typeof SEVERITY_STYLES

  return (
    <Card className={cn('transition-all', SEVERITY_STYLES[severity] ?? '')}>
      <CardContent className="py-3 px-4">
        <div className="flex items-start gap-2">
          {severity === 'critical' && <AlertTriangle className="h-4 w-4 text-red-500 mt-0.5 shrink-0" />}
          {severity === 'warning' && <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5 shrink-0" />}
          {severity === 'info' && <Info className="h-4 w-4 text-blue-500 mt-0.5 shrink-0" />}
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">{insight.title}</p>
            <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
              {insight.description}
            </p>
            {insight.action_label && insight.action_route && (
              <Button
                variant="link"
                size="sm"
                className="h-auto p-0 mt-1 text-xs"
                onClick={() => navigate({ to: insight.action_route! })}
              >
                {insight.action_label}
                <ArrowRight className="h-3 w-3 ml-1" />
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function AIStatusBadge({ status }: { status: CommandCenterResponse['ai_status'] }) {
  if (status === 'operational') {
    return (
      <Badge variant="outline" className="text-green-700 border-green-300 bg-green-50 dark:bg-green-950/30 dark:text-green-400 dark:border-green-800">
        <span className="w-1.5 h-1.5 rounded-full bg-green-500 mr-1.5 animate-pulse" />
        KI aktiv
      </Badge>
    )
  }
  if (status === 'degraded') {
    return (
      <Badge variant="outline" className="text-amber-700 border-amber-300 bg-amber-50 dark:bg-amber-950/30 dark:text-amber-400">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-500 mr-1.5" />
        KI eingeschraenkt
      </Badge>
    )
  }
  return (
    <Badge variant="outline" className="text-red-700 border-red-300 bg-red-50 dark:bg-red-950/30 dark:text-red-400">
      <span className="w-1.5 h-1.5 rounded-full bg-red-500 mr-1.5" />
      KI offline
    </Badge>
  )
}

function LoadingSkeleton() {
  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-6 w-24" />
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-14" />
          ))}
        </div>
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export function CommandCenterView() {
  const navigate = useNavigate()
  const [quickAskQuery, setQuickAskQuery] = useState('')

  const { data, isLoading, error } = useQuery<CommandCenterResponse>({
    queryKey: ['command-center'],
    queryFn: async () => {
      const resp = await apiClient.get<CommandCenterResponse>('/command-center')
      return resp.data
    },
    refetchInterval: 60_000,
    staleTime: 30_000,
  })

  const handleQuickAsk = () => {
    if (!quickAskQuery.trim()) return
    navigate({
      to: '/agent-chat',
      search: { q: quickAskQuery },
    })
    setQuickAskQuery('')
  }

  if (isLoading) return <LoadingSkeleton />

  if (error || !data) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <AlertTriangle className="h-8 w-8 text-amber-500 mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">
            Command Center konnte nicht geladen werden.
          </p>
          <Button
            variant="outline"
            size="sm"
            className="mt-2"
            onClick={() => window.location.reload()}
          >
            Erneut versuchen
          </Button>
        </div>
      </div>
    )
  }

  const today = new Date().toLocaleDateString('de-DE', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Command Center</h1>
          <p className="text-sm text-muted-foreground">{today}</p>
        </div>
        <div className="flex items-center gap-3">
          <AIStatusBadge status={data.ai_status} />
          {data.alert_count > 0 && (
            <Badge variant="destructive" className="text-xs">
              {data.alert_count} {data.alert_count === 1 ? 'Alert' : 'Alerts'}
            </Badge>
          )}
        </div>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {data.kpis.map((kpi) => (
          <KPICardItem key={kpi.id} kpi={kpi} />
        ))}
      </div>

      {/* Main Area */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Priorisierte Aufgaben (2/3) */}
        <Card className="lg:col-span-2">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-primary" />
                Priorisierte Aufgaben
              </CardTitle>
              <span className="text-sm text-muted-foreground">
                Erledigt: {data.task_progress.completed} von {data.task_progress.total}
              </span>
            </div>
            <Progress
              value={data.task_progress.percentage}
              className="h-2 mt-2"
            />
          </CardHeader>
          <CardContent className="pt-0">
            {data.tasks.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                <CheckCircle2 className="h-8 w-8 mb-2 text-green-500" />
                <p className="text-sm font-medium">Alles erledigt!</p>
                <p className="text-xs">Keine offenen Aufgaben fuer heute.</p>
              </div>
            ) : (
              <ScrollArea className="max-h-[400px]">
                <div className="divide-y">
                  {data.tasks.map((task) => (
                    <TaskListItem key={task.id} task={task} />
                  ))}
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </Card>

        {/* Right: Insights & Alerts (1/3) */}
        <div className="space-y-4">
          {/* Alerts */}
          {data.alerts.length > 0 && (
            <Card className="border-red-200 dark:border-red-800">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2 text-red-600 dark:text-red-400">
                  <AlertTriangle className="h-4 w-4" />
                  Aktive Warnungen
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <div className="space-y-2">
                  {data.alerts.slice(0, 5).map((alert) => (
                    <div
                      key={alert.id}
                      className="flex items-center gap-2 text-sm py-1"
                    >
                      <span className={cn(
                        'w-2 h-2 rounded-full shrink-0',
                        alert.severity === 'critical' ? 'bg-red-500' : 'bg-amber-500',
                      )} />
                      <span className="truncate">{alert.title}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Proaktive Insights */}
          <div>
            <h3 className="text-sm font-medium text-muted-foreground mb-3 flex items-center gap-1.5">
              <Info className="h-4 w-4" />
              Proaktive Einblicke
            </h3>
            {data.insights.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                Keine neuen Einblicke.
              </p>
            ) : (
              <div className="space-y-3">
                {data.insights.slice(0, 5).map((insight) => (
                  <InsightCard key={insight.id} insight={insight} />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Quick-Ask Bar */}
      <Card className="border-primary/20">
        <CardContent className="py-3 px-4">
          <div className="flex items-center gap-3">
            <Bot className="h-5 w-5 text-primary shrink-0" />
            <Input
              value={quickAskQuery}
              onChange={(e) => setQuickAskQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleQuickAsk()
              }}
              placeholder="Fragen Sie den KI-Assistenten..."
              className="border-0 shadow-none focus-visible:ring-0 px-0"
            />
            <Button
              size="sm"
              variant="ghost"
              onClick={handleQuickAsk}
              disabled={!quickAskQuery.trim()}
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
