/**
 * Risk Entity Detail Route
 *
 * Detailansicht des Risiko-Scores fuer eine einzelne Entity.
 */

import { createFileRoute, Link, useNavigate } from '@tanstack/react-router';
import { toast } from 'sonner';
import {
  AlertTriangle,
  ArrowLeft,
  RefreshCw,
  Loader2,
  Users,
  Package,
  ExternalLink,
  Calendar,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  useEntityRisk,
  useEntityRiskTrend,
  useCalculateEntityRisk,
  RiskScoreGauge,
  RiskFactorBreakdown,
  EntityRiskMiniChart,
  UI_LABELS,
  RISK_LEVEL_LABELS,
  RISK_LEVEL_COLORS,
} from '@/features/risk-scoring';

export const Route = createFileRoute('/risk/$entityId')({
  component: RiskEntityDetailPage,
});

function RiskEntityDetailPage() {
  const { entityId } = Route.useParams();
  const navigate = useNavigate();

  const {
    data: entityRisk,
    isLoading,
    isError,
    error,
    refetch,
  } = useEntityRisk(entityId);

  const { data: trendData, isLoading: isLoadingTrend } = useEntityRiskTrend(
    entityId,
    30,
    !!entityRisk
  );

  const calculateRisk = useCalculateEntityRisk();

  const handleRecalculate = async () => {
    try {
      await calculateRisk.mutateAsync(entityId);
      toast.success(UI_LABELS.successRecalculate);
    } catch {
      toast.error(UI_LABELS.errorRecalculate);
    }
  };

  if (isError) {
    return (
      <div className="container mx-auto py-8">
        <div className="flex flex-col items-center justify-center gap-4 py-12">
          <AlertTriangle className="h-16 w-16 text-destructive/50" />
          <h2 className="text-xl font-semibold text-destructive">
            Entity nicht gefunden
          </h2>
          <p className="text-muted-foreground">
            {error instanceof Error ? error.message : 'Ein Fehler ist aufgetreten'}
          </p>
          <div className="flex gap-4">
            <Button variant="outline" onClick={() => refetch()}>
              Erneut versuchen
            </Button>
            <Button variant="outline" onClick={() => navigate({ to: '/risk' })}>
              Zurueck zum Dashboard
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (isLoading || !entityRisk) {
    return (
      <div className="container mx-auto py-8">
        <div className="flex items-center gap-4 mb-8">
          <Skeleton className="h-10 w-10" />
          <div className="space-y-2">
            <Skeleton className="h-8 w-64" />
            <Skeleton className="h-4 w-48" />
          </div>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Skeleton className="h-[300px]" />
          <Skeleton className="h-[300px] lg:col-span-2" />
        </div>
      </div>
    );
  }

  const colors = RISK_LEVEL_COLORS[entityRisk.riskLevel];
  const entityDetailPath =
    entityRisk.entityType === 'customer'
      ? '/kunden/$entityId'
      : '/lieferanten/$entityId';

  return (
    <div className="container mx-auto py-8">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-8">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" asChild>
            <Link to="/risk">
              <ArrowLeft className="h-5 w-5" />
            </Link>
          </Button>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold tracking-tight">
                {entityRisk.entityName}
              </h1>
              <Badge variant="outline" className="gap-1">
                {entityRisk.entityType === 'customer' ? (
                  <>
                    <Users className="h-3 w-3" />
                    Kunde
                  </>
                ) : (
                  <>
                    <Package className="h-3 w-3" />
                    Lieferant
                  </>
                )}
              </Badge>
              <Badge className={`${colors.bg} ${colors.text} border-0`}>
                {RISK_LEVEL_LABELS[entityRisk.riskLevel]}
              </Badge>
            </div>
            <p className="text-muted-foreground mt-1 flex items-center gap-2">
              <Calendar className="h-4 w-4" />
              Letzte Berechnung:{' '}
              {entityRisk.calculatedAt.toLocaleString('de-DE')}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" asChild>
            <Link to={entityDetailPath} params={{ entityId }}>
              <ExternalLink className="h-4 w-4 mr-2" />
              Zur Entity
            </Link>
          </Button>
          <Button
            onClick={handleRecalculate}
            disabled={calculateRisk.isPending}
          >
            {calculateRisk.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4 mr-2" />
            )}
            {UI_LABELS.recalculate}
          </Button>
        </div>
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Risk Score Card */}
        <Card>
          <CardHeader>
            <CardTitle>{UI_LABELS.riskScore}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col items-center">
            <RiskScoreGauge score={entityRisk.riskScore} size="lg" />

            {entityRisk.paymentBehaviorScore !== null && (
              <div className="mt-6 pt-6 border-t w-full">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">
                    {UI_LABELS.paymentBehavior}
                  </span>
                  <span className="text-lg font-bold">
                    {entityRisk.paymentBehaviorScore.toFixed(1)}
                  </span>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Risk Factors */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Risikofaktoren</CardTitle>
            <CardDescription>
              Detaillierte Aufschluesselung der Risikobewertung
            </CardDescription>
          </CardHeader>
          <CardContent>
            <RiskFactorBreakdown
              factors={entityRisk.riskFactors}
              showWeights
            />
          </CardContent>
        </Card>

        {/* Trend Chart */}
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Risiko-Verlauf (30 Tage)</CardTitle>
            <CardDescription>
              Entwicklung des Risiko-Scores ueber Zeit
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoadingTrend ? (
              <Skeleton className="h-[200px] w-full" />
            ) : trendData && trendData.length > 0 ? (
              <EntityRiskMiniChart data={trendData} height={200} />
            ) : (
              <div className="h-[200px] flex items-center justify-center text-muted-foreground">
                Keine Verlaufsdaten verfuegbar
              </div>
            )}
          </CardContent>
        </Card>

        {/* Additional Info */}
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Zusaetzliche Informationen</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-2 md:grid-cols-4 gap-6">
              <div>
                <dt className="text-sm text-muted-foreground">Entity-ID</dt>
                <dd className="font-mono text-sm mt-1">{entityRisk.entityId}</dd>
              </div>
              <div>
                <dt className="text-sm text-muted-foreground">Typ</dt>
                <dd className="font-medium mt-1">
                  {entityRisk.entityType === 'customer' ? 'Kunde' : 'Lieferant'}
                </dd>
              </div>
              <div>
                <dt className="text-sm text-muted-foreground">Risikostufe</dt>
                <dd className="mt-1">
                  <Badge className={`${colors.bg} ${colors.text} border-0`}>
                    {RISK_LEVEL_LABELS[entityRisk.riskLevel]}
                  </Badge>
                </dd>
              </div>
              <div>
                <dt className="text-sm text-muted-foreground">Hoch-Risiko</dt>
                <dd className="font-medium mt-1">
                  {entityRisk.isHighRisk ? 'Ja' : 'Nein'}
                </dd>
              </div>
            </dl>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
