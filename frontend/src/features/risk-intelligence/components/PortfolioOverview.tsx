/**
 * Portfolio Overview Component
 *
 * Zeigt Portfolio-Risikouebersicht mit Verteilung und High-Risk Entities.
 */

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Legend,
  Tooltip,
} from 'recharts';
import { Users, TrendingUp, AlertTriangle, DollarSign } from 'lucide-react';
import type { PortfolioRiskOverview } from '../api/risk-intelligence-api';
import { formatCurrencyDE as formatCurrency } from '@/lib/format';

interface PortfolioOverviewProps {
  portfolio: PortfolioRiskOverview;
  className?: string;
}

const COLORS = {
  low: '#22c55e',
  medium: '#eab308',
  high: '#f97316',
  critical: '#ef4444',
};

export function PortfolioOverview({ portfolio, className }: PortfolioOverviewProps) {
  const pieData = [
    { name: 'Niedrig', value: portfolio.risk_distribution.low, color: COLORS.low },
    { name: 'Mittel', value: portfolio.risk_distribution.medium, color: COLORS.medium },
    { name: 'Hoch', value: portfolio.risk_distribution.high, color: COLORS.high },
    { name: 'Kritisch', value: portfolio.risk_distribution.critical, color: COLORS.critical },
  ].filter((d) => d.value > 0);

  const getRiskBadge = (level: string) => {
    const variants: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
      low: 'default',
      medium: 'secondary',
      high: 'outline',
      critical: 'destructive',
    };
    const labels: Record<string, string> = {
      low: 'Niedrig',
      medium: 'Mittel',
      high: 'Hoch',
      critical: 'Kritisch',
    };
    return (
      <Badge variant={variants[level] || 'outline'}>
        {labels[level] || level}
      </Badge>
    );
  };

  return (
    <div className={className}>
      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <Users className="w-5 h-5 text-blue-500" />
              <div>
                <p className="text-sm text-muted-foreground">Entities</p>
                <p className="text-2xl font-bold">{portfolio.total_entities}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-purple-500" />
              <div>
                <p className="text-sm text-muted-foreground">Portfolio-Score</p>
                <p className="text-2xl font-bold">{portfolio.portfolio_risk_score.toFixed(0)}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <DollarSign className="w-5 h-5 text-green-500" />
              <div>
                <p className="text-sm text-muted-foreground">Exposure</p>
                <p className="text-2xl font-bold">{formatCurrency(portfolio.total_exposure)}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-red-500" />
              <div>
                <p className="text-sm text-muted-foreground">High-Risk</p>
                <p className="text-2xl font-bold">{portfolio.high_risk_entities.length}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        {/* Risk Distribution Chart */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Risiko-Verteilung</CardTitle>
            <CardDescription>Verteilung nach Risiko-Level</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={2}
                    dataKey="value"
                  >
                    {pieData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'hsl(var(--card))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                    }}
                    formatter={(value: number) => [`${value} Entities`, '']}
                  />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>

            {/* Distribution Bars */}
            <div className="space-y-2 mt-4">
              {Object.entries(portfolio.risk_distribution).map(([level, count]) => {
                const percentage = portfolio.total_entities > 0
                  ? (count / portfolio.total_entities) * 100
                  : 0;
                return (
                  <div key={level} className="space-y-1">
                    <div className="flex justify-between text-sm">
                      <span className="capitalize">{level === 'low' ? 'Niedrig' : level === 'medium' ? 'Mittel' : level === 'high' ? 'Hoch' : 'Kritisch'}</span>
                      <span>{count} ({percentage.toFixed(0)}%)</span>
                    </div>
                    <Progress
                      value={percentage}
                      className="h-2"
                      style={{
                        ['--progress-background' as string]: COLORS[level as keyof typeof COLORS],
                      }}
                    />
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>

        {/* High Risk Entities */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">High-Risk Entities</CardTitle>
            <CardDescription>Entities mit erhoehtem Risiko</CardDescription>
          </CardHeader>
          <CardContent>
            {portfolio.high_risk_entities.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <AlertTriangle className="w-12 h-12 mx-auto mb-2 opacity-50" />
                <p>Keine High-Risk Entities</p>
                <p className="text-sm">Alle Entities haben ein akzeptables Risiko-Level.</p>
              </div>
            ) : (
              <ScrollArea className="h-64">
                <div className="space-y-3">
                  {portfolio.high_risk_entities.map((entity) => (
                    <div
                      key={entity.entity_id}
                      className="flex items-center justify-between p-3 border rounded-lg hover:bg-muted/50 transition-colors"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="font-medium truncate">{entity.entity_name}</p>
                        <p className="text-sm text-muted-foreground truncate">
                          {entity.primary_concern}
                        </p>
                      </div>
                      <div className="flex items-center gap-2 ml-2">
                        <span className="text-lg font-bold">{entity.risk_score.toFixed(0)}</span>
                        {getRiskBadge(entity.risk_level)}
                      </div>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
