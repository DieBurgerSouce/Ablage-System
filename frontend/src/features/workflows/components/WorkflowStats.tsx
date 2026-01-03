/**
 * WorkflowStats Component
 *
 * Dashboard-Statistiken fuer Workflows.
 */

import { useMemo } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import {
  Play,
  CheckCircle,
  XCircle,
  Clock,
  TrendingUp,
  Activity,
  Zap,
  Calendar,
} from 'lucide-react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { useOverviewStats, useExecutionHistory, useWorkflowStats } from '../hooks/useWorkflows';

interface StatCardProps {
  title: string;
  value: string | number;
  description?: string;
  icon: React.ElementType;
  trend?: number;
  className?: string;
}

function StatCard({ title, value, description, icon: Icon, trend, className }: StatCardProps) {
  return (
    <Card className={className}>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {(description || trend !== undefined) && (
          <p className="text-xs text-muted-foreground mt-1">
            {trend !== undefined && (
              <span
                className={cn(
                  'inline-flex items-center mr-1',
                  trend >= 0 ? 'text-green-600' : 'text-red-600'
                )}
              >
                <TrendingUp
                  className={cn('h-3 w-3 mr-0.5', trend < 0 && 'rotate-180')}
                />
                {Math.abs(trend)}%
              </span>
            )}
            {description}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

const COLORS = ['#22c55e', '#ef4444', '#f59e0b', '#3b82f6', '#8b5cf6'];

interface WorkflowStatsProps {
  workflowId?: string; // If provided, show stats for specific workflow
}

export default function WorkflowStats({ workflowId }: WorkflowStatsProps) {
  const { data: overviewStats, isLoading: overviewLoading } = useOverviewStats();
  const { data: executionHistory, isLoading: historyLoading } = useExecutionHistory(30);
  const { data: workflowStats, isLoading: workflowStatsLoading } = useWorkflowStats(
    workflowId || '',
    !!workflowId
  );

  // Calculate success rate data for pie chart
  const successRateData = useMemo(() => {
    if (!overviewStats) return [];
    const successRate = overviewStats.success_rate || 0;
    return [
      { name: 'Erfolgreich', value: successRate },
      { name: 'Fehlgeschlagen', value: 100 - successRate },
    ];
  }, [overviewStats]);

  // Format execution history for chart
  const chartData = useMemo(() => {
    if (!executionHistory) return [];
    return executionHistory.map((item) => ({
      date: new Date(item.date).toLocaleDateString('de-DE', {
        day: '2-digit',
        month: '2-digit',
      }),
      total: item.total,
      completed: item.completed,
      failed: item.failed,
    }));
  }, [executionHistory]);

  if (overviewLoading || historyLoading) {
    return (
      <div className="space-y-6">
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-80" />
          <Skeleton className="h-80" />
        </div>
      </div>
    );
  }

  // Show specific workflow stats if workflowId provided
  if (workflowId && workflowStats) {
    return (
      <div className="space-y-6">
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <StatCard
            title="Gesamt-Ausfuehrungen"
            value={workflowStats.statistics?.total_executions || 0}
            icon={Play}
          />
          <StatCard
            title="Erfolgreich"
            value={workflowStats.statistics?.completed || 0}
            icon={CheckCircle}
            className="border-green-200 dark:border-green-900"
          />
          <StatCard
            title="Fehlgeschlagen"
            value={workflowStats.statistics?.failed || 0}
            icon={XCircle}
            className="border-red-200 dark:border-red-900"
          />
          <StatCard
            title="Erfolgsrate"
            value={`${(workflowStats.statistics?.success_rate || 0).toFixed(1)}%`}
            icon={TrendingUp}
          />
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Durchschnittliche Ausfuehrungsdauer</CardTitle>
            <CardDescription>
              {workflowStats.statistics?.avg_duration_seconds
                ? `${workflowStats.statistics.avg_duration_seconds.toFixed(1)} Sekunden`
                : 'Keine Daten'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-4">
              <Clock className="h-8 w-8 text-muted-foreground" />
              <div>
                <div className="text-3xl font-bold">
                  {workflowStats.statistics?.avg_duration_seconds
                    ? `${workflowStats.statistics.avg_duration_seconds.toFixed(1)}s`
                    : '-'}
                </div>
                <div className="text-sm text-muted-foreground">
                  Durchschnittlich pro Ausfuehrung
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Overview stats for all workflows
  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Aktive Workflows"
          value={overviewStats?.active_workflows || 0}
          description={`von ${overviewStats?.total_workflows || 0} gesamt`}
          icon={Zap}
        />
        <StatCard
          title="Ausfuehrungen heute"
          value={overviewStats?.executions_today || 0}
          icon={Calendar}
        />
        <StatCard
          title="Gesamt-Ausfuehrungen"
          value={overviewStats?.total_executions || 0}
          icon={Activity}
        />
        <StatCard
          title="Erfolgsrate"
          value={`${(overviewStats?.success_rate || 0).toFixed(1)}%`}
          icon={TrendingUp}
        />
      </div>

      {/* Charts */}
      <div className="grid gap-4 md:grid-cols-2">
        {/* Execution History Chart */}
        <Card>
          <CardHeader>
            <CardTitle>Ausfuehrungs-Verlauf</CardTitle>
            <CardDescription>Letzte 30 Tage</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 12 }}
                    tickLine={false}
                    className="text-muted-foreground"
                  />
                  <YAxis
                    tick={{ fontSize: 12 }}
                    tickLine={false}
                    className="text-muted-foreground"
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'hsl(var(--background))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '6px',
                    }}
                  />
                  <Bar
                    dataKey="completed"
                    name="Erfolgreich"
                    fill="#22c55e"
                    radius={[4, 4, 0, 0]}
                  />
                  <Bar
                    dataKey="failed"
                    name="Fehlgeschlagen"
                    fill="#ef4444"
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Success Rate Pie Chart */}
        <Card>
          <CardHeader>
            <CardTitle>Erfolgsrate</CardTitle>
            <CardDescription>Verhaeltnis erfolgreicher Ausfuehrungen</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-64 flex items-center justify-center">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={successRateData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={2}
                    dataKey="value"
                    label={({ name, value }) => `${name}: ${value.toFixed(1)}%`}
                    labelLine={false}
                  >
                    {successRateData.map((entry, index) => (
                      <Cell key={entry.name} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value: number) => `${value.toFixed(1)}%`}
                    contentStyle={{
                      backgroundColor: 'hsl(var(--background))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '6px',
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Trend Line Chart */}
      <Card>
        <CardHeader>
          <CardTitle>Ausfuehrungs-Trend</CardTitle>
          <CardDescription>Taegliche Ausfuehrungen der letzten 30 Tage</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 12 }}
                  tickLine={false}
                  className="text-muted-foreground"
                />
                <YAxis
                  tick={{ fontSize: 12 }}
                  tickLine={false}
                  className="text-muted-foreground"
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'hsl(var(--background))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '6px',
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="total"
                  name="Gesamt"
                  stroke="#3b82f6"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="completed"
                  name="Erfolgreich"
                  stroke="#22c55e"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
