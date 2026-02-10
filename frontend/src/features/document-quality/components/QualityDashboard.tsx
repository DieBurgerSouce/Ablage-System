/**
 * QualityDashboard Component
 *
 * Unternehmensweites Datenqualitaets-Dashboard:
 * - KPI-Karten: Gesamte Dokumente, Durchschnitt, GRUEN-Anteil, ROT-Dokumente
 * - Ampel-Verteilung als farbige Balken
 */

import { cn } from '@/lib/utils';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { useCompanyQualityOverview, formatScorePercent } from '../hooks/useDocumentQuality';
import type { AmpelVerteilung } from '../types/quality-types';

// =============================================================================
// Number Formatter
// =============================================================================

const numberFormatter = new Intl.NumberFormat('de-DE');

function formatNumber(value: number): string {
  return numberFormatter.format(value);
}

function formatProzent(value: number): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'percent',
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(value / 100);
}

// =============================================================================
// KPI Card
// =============================================================================

interface KpiCardProps {
  title: string;
  value: string;
  description?: string;
  highlight?: boolean;
  className?: string;
}

function KpiCard({ title, value, description, highlight, className }: KpiCardProps) {
  return (
    <Card className={cn(highlight && 'border-red-500/50', className)}>
      <CardHeader className="pb-2">
        <CardDescription>{title}</CardDescription>
      </CardHeader>
      <CardContent>
        <div
          className={cn(
            'text-2xl font-bold',
            highlight && 'text-red-600 dark:text-red-400',
          )}
        >
          {value}
        </div>
        {description && (
          <p className="mt-1 text-xs text-muted-foreground">{description}</p>
        )}
      </CardContent>
    </Card>
  );
}

// =============================================================================
// Ampel Distribution Bar
// =============================================================================

interface AmpelDistributionProps {
  verteilung: AmpelVerteilung;
}

function AmpelDistribution({ verteilung }: AmpelDistributionProps) {
  const categories = [
    {
      key: 'gruen' as const,
      label: 'Gruen',
      data: verteilung.gruen,
      bgClass: 'bg-green-500',
      textClass: 'text-green-700 dark:text-green-400',
    },
    {
      key: 'gelb' as const,
      label: 'Gelb',
      data: verteilung.gelb,
      bgClass: 'bg-yellow-500',
      textClass: 'text-yellow-700 dark:text-yellow-400',
    },
    {
      key: 'rot' as const,
      label: 'Rot',
      data: verteilung.rot,
      bgClass: 'bg-red-500',
      textClass: 'text-red-700 dark:text-red-400',
    },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Ampel-Verteilung</CardTitle>
        <CardDescription>
          Qualitaetsverteilung aller bewerteten Dokumente
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Stacked bar */}
        <div className="flex h-8 w-full overflow-hidden rounded-full">
          {categories.map((cat) =>
            cat.data.prozent > 0 ? (
              <div
                key={cat.key}
                className={cn('flex items-center justify-center text-xs font-medium text-white', cat.bgClass)}
                style={{ width: `${cat.data.prozent}%` }}
              >
                {cat.data.prozent >= 10 && formatProzent(cat.data.prozent)}
              </div>
            ) : null,
          )}
        </div>

        {/* Legend */}
        <div className="grid grid-cols-3 gap-4">
          {categories.map((cat) => (
            <div key={cat.key} className="space-y-1">
              <div className="flex items-center gap-2">
                <span className={cn('h-3 w-3 rounded-full', cat.bgClass)} />
                <span className="text-sm font-medium">{cat.label}</span>
              </div>
              <div className={cn('text-lg font-bold', cat.textClass)}>
                {formatNumber(cat.data.anzahl)}
              </div>
              <div className="text-xs text-muted-foreground">
                {formatProzent(cat.data.prozent)}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// =============================================================================
// Main Dashboard Component
// =============================================================================

export function QualityDashboard() {
  const { data: overview, isLoading, isError, error } = useCompanyQualityOverview();

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i} className="animate-pulse">
              <CardHeader className="pb-2">
                <div className="h-4 w-24 rounded bg-muted" />
              </CardHeader>
              <CardContent>
                <div className="h-8 w-16 rounded bg-muted" />
              </CardContent>
            </Card>
          ))}
        </div>
        <Card className="animate-pulse">
          <CardHeader>
            <div className="h-5 w-40 rounded bg-muted" />
          </CardHeader>
          <CardContent>
            <div className="h-8 w-full rounded bg-muted" />
          </CardContent>
        </Card>
      </div>
    );
  }

  if (isError) {
    return (
      <Card className="border-destructive">
        <CardHeader>
          <CardTitle className="text-destructive">Fehler</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            {error?.message || 'Qualitaetsuebersicht konnte nicht geladen werden.'}
          </p>
        </CardContent>
      </Card>
    );
  }

  if (!overview) {
    return null;
  }

  const rotAnzahl = overview.verteilung.rot.anzahl;

  return (
    <div className="space-y-6">
      {/* KPI Row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          title="Gesamte Dokumente"
          value={formatNumber(overview.total_documents)}
          description="Bewertete Dokumente"
        />
        <KpiCard
          title="Durchschnittliche Qualitaet"
          value={formatScorePercent(overview.average_score)}
          description="Ueber alle Dokumente"
        />
        <KpiCard
          title="GRUEN-Anteil"
          value={formatProzent(overview.verteilung.gruen.prozent)}
          description={`${formatNumber(overview.verteilung.gruen.anzahl)} Dokumente`}
        />
        <KpiCard
          title="ROT-Dokumente"
          value={formatNumber(rotAnzahl)}
          description="Manuelle Korrektur erforderlich"
          highlight={rotAnzahl > 0}
        />
      </div>

      {/* Ampel Distribution */}
      <AmpelDistribution verteilung={overview.verteilung} />
    </div>
  );
}
