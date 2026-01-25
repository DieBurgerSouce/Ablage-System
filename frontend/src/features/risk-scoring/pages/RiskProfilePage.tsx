/**
 * Risk Profile Page Component
 *
 * Vollstaendige Seite fuer detaillierte Risiko-Analyse eines Geschaeftspartners.
 */

import { useParams } from '@tanstack/react-router';
import {
  AlertTriangle,
  RefreshCw,
  TrendingUp,
  Calendar,
  ArrowLeft,
  Loader2,
} from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Separator } from '@/components/ui/separator';
import { RiskScoreGauge } from '../components/RiskScoreGauge';
import { RiskFactorBreakdown } from '../components/RiskFactorBreakdown';
import { RiskAlertBanner } from '../components/RiskAlertBanner';
import { EntityRiskMiniChart } from '../components/RiskTrendChart';
import {
  useEntityRisk,
  useEntityRiskTrend,
  useCalculateEntityRisk,
} from '../hooks/use-risk-queries';
import { UI_LABELS, RISK_LEVEL_LABELS, RISK_LEVEL_COLORS } from '../types/risk-types';

interface RiskProfilePageProps {
  entityId?: string;
  showBackButton?: boolean;
  onBack?: () => void;
  className?: string;
}

export function RiskProfilePage({
  entityId: propEntityId,
  showBackButton = true,
  onBack,
  className,
}: RiskProfilePageProps) {
  // Get entityId from params or props
  const params = useParams({ strict: false });
  const entityId = propEntityId || (params as { entityId?: string }).entityId;

  const {
    data: entityRisk,
    isLoading,
    isError,
    error,
    refetch,
  } = useEntityRisk(entityId || '', !!entityId);

  const { data: trendData, isLoading: isTrendLoading } = useEntityRiskTrend(
    entityId || '',
    30,
    !!entityId
  );

  const calculateMutation = useCalculateEntityRisk();

  const handleRecalculate = async () => {
    if (!entityId) return;

    try {
      await calculateMutation.mutateAsync(entityId);
      toast.success(UI_LABELS.successRecalculate);
    } catch {
      toast.error(UI_LABELS.errorRecalculate);
    }
  };

  if (!entityId) {
    return (
      <div className={cn('flex flex-col items-center justify-center py-12', className)}>
        <AlertTriangle className="h-16 w-16 text-destructive/50 mb-4" />
        <h2 className="text-xl font-semibold">Keine Entity-ID angegeben</h2>
        <p className="text-muted-foreground mt-1">
          Bitte wählen Sie einen Geschäftspartner aus.
        </p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className={cn('flex flex-col items-center justify-center py-12', className)}>
        <AlertTriangle className="h-16 w-16 text-destructive/50 mb-4" />
        <h2 className="text-xl font-semibold text-destructive">
          {UI_LABELS.errorLoad}
        </h2>
        <p className="text-muted-foreground mt-1">
          {error instanceof Error ? error.message : 'Ein Fehler ist aufgetreten'}
        </p>
        <Button variant="outline" onClick={() => refetch()} className="mt-4">
          Erneut versuchen
        </Button>
      </div>
    );
  }

  if (isLoading || !entityRisk) {
    return (
      <div className={cn('space-y-6', className)}>
        <Skeleton className="h-12 w-full" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Skeleton className="h-[300px]" />
          <Skeleton className="h-[300px]" />
          <Skeleton className="h-[300px]" />
        </div>
        <Skeleton className="h-[400px]" />
      </div>
    );
  }

  const colors = RISK_LEVEL_COLORS[entityRisk.riskLevel];

  return (
    <div className={cn('space-y-6', className)}>
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-3">
          {showBackButton && onBack && (
            <Button
              variant="ghost"
              size="icon"
              onClick={onBack}
              className="flex-shrink-0"
            >
              <ArrowLeft className="h-5 w-5" />
            </Button>
          )}
          <div>
            <h1 className="text-2xl font-bold">{entityRisk.entityName}</h1>
            <p className="text-muted-foreground">
              {entityRisk.entityType === 'customer' ? 'Kunde' : 'Lieferant'} -{' '}
              Risiko-Profil
            </p>
          </div>
        </div>
        <Button
          onClick={handleRecalculate}
          disabled={calculateMutation.isPending}
          variant="outline"
        >
          {calculateMutation.isPending ? (
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4 mr-2" />
          )}
          {UI_LABELS.recalculate}
        </Button>
      </div>

      {/* Alert Banner */}
      {(entityRisk.riskLevel === 'high' || entityRisk.riskLevel === 'critical') && (
        <RiskAlertBanner entityRisk={entityRisk} />
      )}

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Risk Score Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5" />
              {UI_LABELS.riskScore}
            </CardTitle>
            <CardDescription>Aktueller Risiko-Score und Stufe</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="flex justify-center">
              <RiskScoreGauge score={entityRisk.riskScore} size="lg" />
            </div>

            <Separator />

            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Risikostufe</span>
                <span
                  className={cn(
                    'px-3 py-1 rounded-full text-sm font-medium',
                    colors.bg,
                    colors.text
                  )}
                >
                  {RISK_LEVEL_LABELS[entityRisk.riskLevel]}
                </span>
              </div>

              {entityRisk.paymentBehaviorScore !== null && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">
                    Zahlungsverhalten
                  </span>
                  <span className="font-medium">
                    {entityRisk.paymentBehaviorScore.toFixed(1)} / 100
                  </span>
                </div>
              )}

              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">
                  <Calendar className="h-3 w-3 inline mr-1" />
                  Berechnet am
                </span>
                <span className="text-sm font-medium">
                  {entityRisk.calculatedAt.toLocaleDateString('de-DE', {
                    day: '2-digit',
                    month: '2-digit',
                    year: 'numeric',
                  })}
                </span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Risk Factors Card */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Risikofaktoren im Detail</CardTitle>
            <CardDescription>
              Aufschlüsselung nach den 5 Haupt-Risikofaktoren
            </CardDescription>
          </CardHeader>
          <CardContent>
            <RiskFactorBreakdown
              factors={entityRisk.riskFactors}
              showWeights
            />
          </CardContent>
        </Card>
      </div>

      {/* Trend Chart */}
      {trendData && trendData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Risiko-Verlauf (30 Tage)</CardTitle>
            <CardDescription>
              Entwicklung des Risiko-Scores über die letzten 30 Tage
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isTrendLoading ? (
              <Skeleton className="h-[200px] w-full" />
            ) : (
              <EntityRiskMiniChart data={trendData} height={200} />
            )}
          </CardContent>
        </Card>
      )}

      {/* Additional Information */}
      <Card>
        <CardHeader>
          <CardTitle>Zusätzliche Informationen</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Risk Factor Details */}
            <div className="space-y-3">
              <h3 className="font-medium text-sm">Faktor-Details</h3>
              <div className="space-y-2 text-sm">
                {entityRisk.riskFactors.map((factor) => (
                  <div
                    key={factor.name}
                    className="flex items-center justify-between p-2 rounded-md bg-muted/50"
                  >
                    <span className="text-muted-foreground">
                      {getFactorLabel(factor.name)}
                    </span>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">
                        {formatRawValue(factor)}
                      </span>
                      <span className="font-medium">
                        +{factor.contribution.toFixed(1)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Risk Interpretation */}
            <div className="space-y-3">
              <h3 className="font-medium text-sm">Interpretation</h3>
              <div className="text-sm text-muted-foreground space-y-2">
                <p>
                  {getRiskInterpretation(
                    entityRisk.riskScore,
                    entityRisk.riskLevel
                  )}
                </p>
                {entityRisk.isHighRisk && (
                  <p className={cn('font-medium', colors.text)}>
                    ⚠️ Dieser Geschäftspartner erfordert besondere Aufmerksamkeit.
                  </p>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

/**
 * Helper Functions
 */

function getFactorLabel(factor: string): string {
  const labels: Record<string, string> = {
    payment_delay: 'Zahlungsverzögerung',
    default_rate: 'Ausfallrate',
    invoice_volume: 'Rechnungsvolumen',
    document_frequency: 'Dokumenthäufigkeit',
    relationship_age: 'Beziehungsdauer',
  };
  return labels[factor] || factor;
}

function formatRawValue(factor: { name: string; rawValue?: number | string }): string {
  if (factor.rawValue === undefined || factor.rawValue === null) {
    return '-';
  }

  switch (factor.name) {
    case 'payment_delay':
      return `${factor.rawValue} Tage`;
    case 'default_rate':
      return `${(Number(factor.rawValue) * 100).toFixed(1)}%`;
    case 'invoice_volume':
      return new Intl.NumberFormat('de-DE', {
        style: 'currency',
        currency: 'EUR',
        maximumFractionDigits: 0,
      }).format(Number(factor.rawValue));
    case 'document_frequency':
      return `${factor.rawValue}/Monat`;
    case 'relationship_age':
      return `${factor.rawValue} Monate`;
    default:
      return String(factor.rawValue);
  }
}

function getRiskInterpretation(score: number, level: string): string {
  if (level === 'critical') {
    return `Mit einem Risiko-Score von ${score.toFixed(
      1
    )} befindet sich dieser Geschäftspartner in der kritischen Zone. Sofortige Maßnahmen zur Risikominimierung werden dringend empfohlen.`;
  }

  if (level === 'high') {
    return `Ein Risiko-Score von ${score.toFixed(
      1
    )} deutet auf erhöhtes Risiko hin. Eine engere Überwachung und präventive Maßnahmen sind ratsam.`;
  }

  if (level === 'medium') {
    return `Der Risiko-Score von ${score.toFixed(
      1
    )} liegt im mittleren Bereich. Die Geschäftsbeziehung sollte regelmäßig überprüft werden.`;
  }

  return `Mit einem Risiko-Score von ${score.toFixed(
    1
  )} weist dieser Geschäftspartner ein niedriges Risiko auf. Die Geschäftsbeziehung verläuft stabil.`;
}
