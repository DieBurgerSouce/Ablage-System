/**
 * PredictiveInsights Dashboard Component.
 *
 * Zeigt KI-basierte Vorhersagen und Einblicke:
 * - Cashflow-Prognosen
 * - Kommende Fristen
 * - Wartungsvorhersagen
 * - Kostentrends
 */

import React, { useMemo } from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import {
  TrendingUp,
  TrendingDown,
  Calendar,
  Car,
  Home,
  Shield,
  AlertTriangle,
  CheckCircle,
  Clock,
  Euro,
} from 'lucide-react';

interface CashFlowPrediction {
  month: string;
  predictedIncome: number;
  predictedExpenses: number;
  predictedNet: number;
  confidence: number;
}

interface UpcomingDeadline {
  id: string;
  title: string;
  dueDate: string;
  daysUntil: number;
  type: 'insurance' | 'property' | 'vehicle' | 'finance' | 'other';
  severity: 'low' | 'medium' | 'high' | 'critical';
}

interface MaintenancePrediction {
  entityId: string;
  entityType: 'vehicle' | 'property';
  entityName: string;
  predictedDate: string;
  predictedCost: number;
  serviceType: string;
  confidence: number;
}

interface CostTrend {
  category: string;
  currentMonthly: number;
  previousMonthly: number;
  trend: 'up' | 'down' | 'stable';
  changePercent: number;
}

interface PredictiveInsightsProps {
  cashFlowPredictions: CashFlowPrediction[];
  upcomingDeadlines: UpcomingDeadline[];
  maintenancePredictions: MaintenancePrediction[];
  costTrends: CostTrend[];
  isLoading?: boolean;
}

const formatCurrency = (value: number): string => {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
};

const formatDate = (dateStr: string): string => {
  return new Date(dateStr).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
};

const getDeadlineIcon = (type: UpcomingDeadline['type']) => {
  switch (type) {
    case 'insurance':
      return <Shield className="h-4 w-4" />;
    case 'property':
      return <Home className="h-4 w-4" />;
    case 'vehicle':
      return <Car className="h-4 w-4" />;
    case 'finance':
      return <Euro className="h-4 w-4" />;
    default:
      return <Calendar className="h-4 w-4" />;
  }
};

const getSeverityColor = (severity: UpcomingDeadline['severity']): string => {
  switch (severity) {
    case 'critical':
      return 'bg-red-500';
    case 'high':
      return 'bg-orange-500';
    case 'medium':
      return 'bg-yellow-500';
    case 'low':
      return 'bg-green-500';
    default:
      return 'bg-gray-500';
  }
};

const getSeverityLabel = (severity: UpcomingDeadline['severity']): string => {
  switch (severity) {
    case 'critical':
      return 'Kritisch';
    case 'high':
      return 'Hoch';
    case 'medium':
      return 'Mittel';
    case 'low':
      return 'Niedrig';
    default:
      return 'Unbekannt';
  }
};

export const PredictiveInsights: React.FC<PredictiveInsightsProps> = ({
  cashFlowPredictions,
  upcomingDeadlines,
  maintenancePredictions,
  costTrends,
  isLoading = false,
}) => {
  // Berechne Zusammenfassung
  const summary = useMemo(() => {
    const totalPredictedNet = cashFlowPredictions.reduce(
      (sum, p) => sum + p.predictedNet,
      0
    );
    const urgentDeadlines = upcomingDeadlines.filter(
      (d) => d.severity === 'critical' || d.severity === 'high'
    ).length;
    const upcomingMaintenance = maintenancePredictions.filter(
      (m) => new Date(m.predictedDate) <= new Date(Date.now() + 30 * 24 * 60 * 60 * 1000)
    ).length;
    const risingCosts = costTrends.filter((t) => t.trend === 'up').length;

    return {
      totalPredictedNet,
      urgentDeadlines,
      upcomingMaintenance,
      risingCosts,
    };
  }, [cashFlowPredictions, upcomingDeadlines, maintenancePredictions, costTrends]);

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <Card key={i}>
            <CardHeader>
              <Skeleton className="h-4 w-24" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-full mb-2" />
              <Skeleton className="h-4 w-3/4" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Cashflow Prognose */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Cashflow Prognose (3 Monate)
            </CardTitle>
            {summary.totalPredictedNet >= 0 ? (
              <TrendingUp className="h-4 w-4 text-green-500" />
            ) : (
              <TrendingDown className="h-4 w-4 text-red-500" />
            )}
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${
              summary.totalPredictedNet >= 0 ? 'text-green-600' : 'text-red-600'
            }`}>
              {formatCurrency(summary.totalPredictedNet)}
            </div>
            <p className="text-xs text-muted-foreground">
              Erwarteter Netto-Cashflow
            </p>
          </CardContent>
        </Card>

        {/* Dringende Fristen */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Dringende Fristen
            </CardTitle>
            {summary.urgentDeadlines > 0 ? (
              <AlertTriangle className="h-4 w-4 text-orange-500" />
            ) : (
              <CheckCircle className="h-4 w-4 text-green-500" />
            )}
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {summary.urgentDeadlines}
            </div>
            <p className="text-xs text-muted-foreground">
              {summary.urgentDeadlines === 0
                ? 'Keine dringenden Fristen'
                : 'Erfordern Aufmerksamkeit'}
            </p>
          </CardContent>
        </Card>

        {/* Anstehende Wartungen */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Wartungen (30 Tage)
            </CardTitle>
            <Clock className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {summary.upcomingMaintenance}
            </div>
            <p className="text-xs text-muted-foreground">
              Geplante Wartungstermine
            </p>
          </CardContent>
        </Card>

        {/* Steigende Kosten */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Kostentrends
            </CardTitle>
            <TrendingUp className="h-4 w-4 text-yellow-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {summary.risingCosts} / {costTrends.length}
            </div>
            <p className="text-xs text-muted-foreground">
              Kategorien mit steigenden Kosten
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Detailed Sections */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Cashflow Prognose Detail */}
        <Card>
          <CardHeader>
            <CardTitle>Cashflow-Prognose</CardTitle>
            <CardDescription>
              Erwartete Einnahmen und Ausgaben der naechsten Monate
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {cashFlowPredictions.map((prediction, index) => (
                <div key={index} className="space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="font-medium">{prediction.month}</span>
                    <Badge variant={prediction.predictedNet >= 0 ? 'default' : 'destructive'}>
                      {formatCurrency(prediction.predictedNet)}
                    </Badge>
                  </div>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Einnahmen:</span>
                      <span className="text-green-600">
                        {formatCurrency(prediction.predictedIncome)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Ausgaben:</span>
                      <span className="text-red-600">
                        {formatCurrency(prediction.predictedExpenses)}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">Konfidenz:</span>
                    <Progress value={prediction.confidence * 100} className="h-1 flex-1" />
                    <span className="text-xs">{Math.round(prediction.confidence * 100)}%</span>
                  </div>
                </div>
              ))}
              {cashFlowPredictions.length === 0 && (
                <p className="text-muted-foreground text-center py-4">
                  Keine Prognosen verfuegbar
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Anstehende Fristen */}
        <Card>
          <CardHeader>
            <CardTitle>Anstehende Fristen</CardTitle>
            <CardDescription>
              Wichtige Termine und Deadlines
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {upcomingDeadlines.slice(0, 5).map((deadline) => (
                <div
                  key={deadline.id}
                  className="flex items-center gap-3 p-2 rounded-lg bg-muted/50"
                >
                  <div className={`p-2 rounded-full ${getSeverityColor(deadline.severity)}`}>
                    {getDeadlineIcon(deadline.type)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate">{deadline.title}</p>
                    <p className="text-sm text-muted-foreground">
                      {formatDate(deadline.dueDate)}
                    </p>
                  </div>
                  <div className="text-right">
                    <Badge variant="outline">
                      {deadline.daysUntil} Tage
                    </Badge>
                    <p className="text-xs text-muted-foreground mt-1">
                      {getSeverityLabel(deadline.severity)}
                    </p>
                  </div>
                </div>
              ))}
              {upcomingDeadlines.length === 0 && (
                <p className="text-muted-foreground text-center py-4">
                  Keine anstehenden Fristen
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Wartungsvorhersagen */}
        <Card>
          <CardHeader>
            <CardTitle>Wartungsvorhersagen</CardTitle>
            <CardDescription>
              Prognostizierte Wartungstermine und Kosten
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {maintenancePredictions.slice(0, 5).map((maintenance) => (
                <div
                  key={maintenance.entityId}
                  className="flex items-center gap-3 p-2 rounded-lg bg-muted/50"
                >
                  <div className="p-2 rounded-full bg-blue-500">
                    {maintenance.entityType === 'vehicle' ? (
                      <Car className="h-4 w-4 text-white" />
                    ) : (
                      <Home className="h-4 w-4 text-white" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate">{maintenance.entityName}</p>
                    <p className="text-sm text-muted-foreground">
                      {maintenance.serviceType}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="font-medium">{formatCurrency(maintenance.predictedCost)}</p>
                    <p className="text-xs text-muted-foreground">
                      {formatDate(maintenance.predictedDate)}
                    </p>
                  </div>
                </div>
              ))}
              {maintenancePredictions.length === 0 && (
                <p className="text-muted-foreground text-center py-4">
                  Keine Wartungen prognostiziert
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Kostentrends */}
        <Card>
          <CardHeader>
            <CardTitle>Kostentrends</CardTitle>
            <CardDescription>
              Entwicklung der monatlichen Ausgaben nach Kategorie
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {costTrends.map((trend, index) => (
                <div
                  key={index}
                  className="flex items-center gap-3 p-2 rounded-lg bg-muted/50"
                >
                  <div className={`p-2 rounded-full ${
                    trend.trend === 'up'
                      ? 'bg-red-500'
                      : trend.trend === 'down'
                      ? 'bg-green-500'
                      : 'bg-gray-500'
                  }`}>
                    {trend.trend === 'up' ? (
                      <TrendingUp className="h-4 w-4 text-white" />
                    ) : trend.trend === 'down' ? (
                      <TrendingDown className="h-4 w-4 text-white" />
                    ) : (
                      <div className="h-4 w-4 border-t-2 border-white" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate">{trend.category}</p>
                    <p className="text-sm text-muted-foreground">
                      Vormonat: {formatCurrency(trend.previousMonthly)}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="font-medium">{formatCurrency(trend.currentMonthly)}</p>
                    <p className={`text-xs ${
                      trend.trend === 'up'
                        ? 'text-red-500'
                        : trend.trend === 'down'
                        ? 'text-green-500'
                        : 'text-muted-foreground'
                    }`}>
                      {trend.trend === 'up' ? '+' : ''}{trend.changePercent.toFixed(1)}%
                    </p>
                  </div>
                </div>
              ))}
              {costTrends.length === 0 && (
                <p className="text-muted-foreground text-center py-4">
                  Keine Kostendaten verfuegbar
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default PredictiveInsights;
