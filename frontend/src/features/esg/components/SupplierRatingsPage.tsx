/**
 * Supplier Ratings Page
 *
 * ESG-Bewertungen und Ratings von Lieferanten.
 * Verbunden mit der ESG API via TanStack Query Hooks.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Plus, Download, Filter, Star, AlertTriangle, CheckCircle, AlertCircle } from 'lucide-react';
import {
  useSupplierRatings,
  useSupplierRiskSummary,
} from '../hooks/use-esg-queries';

export function SupplierRatingsPage() {
  const { data: riskSummary, isLoading: summaryLoading, error: summaryError } = useSupplierRiskSummary();
  const { data: ratings, isLoading: ratingsLoading } = useSupplierRatings({ limit: 50 });

  if (summaryError) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>
          Fehler beim Laden der Lieferanten-Bewertungen: {summaryError.message}
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      {/* Actions */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Lieferanten-Bewertung</h2>
          <p className="text-sm text-muted-foreground">
            ESG-Ratings und Risikobewertung Ihrer Lieferanten
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" disabled title="Kommt bald" aria-label="Lieferanten filtern">
            <Filter className="h-4 w-4 mr-2" />
            Filter
          </Button>
          <Button variant="outline" size="sm" disabled title="Kommt bald" aria-label="Lieferanten exportieren">
            <Download className="h-4 w-4 mr-2" />
            Export
          </Button>
          <Button size="sm" disabled title="Kommt bald" aria-label="Bewertung anfordern">
            <Plus className="h-4 w-4 mr-2" />
            Bewertung anfordern
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Gesamt-Lieferanten</CardTitle>
          </CardHeader>
          <CardContent>
            {summaryLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <div className="text-2xl font-bold">{riskSummary?.total_suppliers ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <CheckCircle className="h-4 w-4 text-green-600" />
              Niedriges Risiko
            </CardTitle>
          </CardHeader>
          <CardContent>
            {summaryLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <div className="text-2xl font-bold text-green-600">
                {riskSummary?.low_risk_count ?? 0}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-600" />
              Mittleres Risiko
            </CardTitle>
          </CardHeader>
          <CardContent>
            {summaryLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <div className="text-2xl font-bold text-amber-600">
                {riskSummary?.medium_risk_count ?? 0}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Star className="h-4 w-4 text-red-600" />
              Hohes Risiko
            </CardTitle>
          </CardHeader>
          <CardContent>
            {summaryLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <div className="text-2xl font-bold text-red-600">
                {(riskSummary?.high_risk_count ?? 0) + (riskSummary?.critical_risk_count ?? 0)}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Rating Distribution */}
      <Card>
        <CardHeader>
          <CardTitle>Rating-Verteilung</CardTitle>
          <CardDescription>
            ESG-Scores nach Risiko-Level
          </CardDescription>
        </CardHeader>
        <CardContent>
          {summaryLoading ? (
            <Skeleton className="h-[200px] w-full" />
          ) : riskSummary ? (
            <div className="h-[200px] flex items-end justify-around gap-4 pb-8" role="img" aria-label="Risiko-Verteilung der Lieferanten">
              <div className="flex flex-col items-center">
                <div
                  className="w-16 bg-green-500 rounded-t transition-all"
                  style={{ height: `${Math.max((riskSummary.low_risk_count / Math.max(riskSummary.total_suppliers, 1)) * 150, 10)}px` }}
                />
                <span className="text-sm font-medium mt-2">Niedrig</span>
                <span className="text-xs text-muted-foreground">{riskSummary.low_risk_count}</span>
              </div>
              <div className="flex flex-col items-center">
                <div
                  className="w-16 bg-amber-500 rounded-t transition-all"
                  style={{ height: `${Math.max((riskSummary.medium_risk_count / Math.max(riskSummary.total_suppliers, 1)) * 150, 10)}px` }}
                />
                <span className="text-sm font-medium mt-2">Mittel</span>
                <span className="text-xs text-muted-foreground">{riskSummary.medium_risk_count}</span>
              </div>
              <div className="flex flex-col items-center">
                <div
                  className="w-16 bg-orange-500 rounded-t transition-all"
                  style={{ height: `${Math.max((riskSummary.high_risk_count / Math.max(riskSummary.total_suppliers, 1)) * 150, 10)}px` }}
                />
                <span className="text-sm font-medium mt-2">Hoch</span>
                <span className="text-xs text-muted-foreground">{riskSummary.high_risk_count}</span>
              </div>
              <div className="flex flex-col items-center">
                <div
                  className="w-16 bg-red-500 rounded-t transition-all"
                  style={{ height: `${Math.max((riskSummary.critical_risk_count / Math.max(riskSummary.total_suppliers, 1)) * 150, 10)}px` }}
                />
                <span className="text-sm font-medium mt-2">Kritisch</span>
                <span className="text-xs text-muted-foreground">{riskSummary.critical_risk_count}</span>
              </div>
            </div>
          ) : (
            <div className="h-[200px] flex items-center justify-center text-muted-foreground">
              Keine Daten vorhanden
            </div>
          )}
        </CardContent>
      </Card>

      {/* Suppliers Table */}
      <Card>
        <CardHeader>
          <CardTitle>Lieferanten-Übersicht</CardTitle>
          <CardDescription>
            Alle Lieferanten mit ihren ESG-Bewertungen
          </CardDescription>
        </CardHeader>
        <CardContent>
          {ratingsLoading ? (
            <div className="space-y-4">
              {[...Array(3)].map((_, i) => (
                <Skeleton key={i} className="h-20 w-full" />
              ))}
            </div>
          ) : ratings?.items && ratings.items.length > 0 ? (
            <div className="space-y-4">
              {ratings.items.map((rating) => (
                <div
                  key={rating.id}
                  className="flex items-center justify-between p-4 border rounded-lg hover:bg-muted/50 transition-colors"
                >
                  <div>
                    <p className="font-medium">{rating.entity_name || 'Unbekannter Lieferant'}</p>
                    <p className="text-sm text-muted-foreground">
                      Bewertet am {formatDate(rating.rating_date)}
                    </p>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      <p className="text-sm font-medium">ESG Score</p>
                      <p className={`text-lg font-bold ${getScoreColor(rating.overall_score)}`}>
                        {rating.overall_score?.toFixed(0) ?? 0}/100
                      </p>
                    </div>
                    <Badge className={getRiskBadgeClass(rating.risk_level)}>
                      {getRiskLabel(rating.risk_level)}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              Keine Lieferanten-Bewertungen vorhanden
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// Helper functions
function formatDate(dateString?: string): string {
  if (!dateString) return '-';
  return new Intl.DateTimeFormat('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(dateString));
}

function getScoreColor(score?: number): string {
  if (score === undefined || score === null) return 'text-gray-600';
  if (score >= 70) return 'text-green-600';
  if (score >= 50) return 'text-amber-600';
  return 'text-red-600';
}

function getRiskLabel(riskLevel?: string): string {
  const labels: Record<string, string> = {
    low: 'Niedrig',
    medium: 'Mittel',
    high: 'Hoch',
    critical: 'Kritisch',
  };
  return labels[riskLevel ?? ''] || riskLevel || 'Unbekannt';
}

function getRiskBadgeClass(riskLevel?: string): string {
  const classes: Record<string, string> = {
    low: 'bg-green-600 hover:bg-green-700',
    medium: 'bg-amber-100 text-amber-800 hover:bg-amber-200',
    high: 'bg-orange-100 text-orange-800 hover:bg-orange-200',
    critical: 'bg-red-600 hover:bg-red-700',
  };
  return classes[riskLevel ?? ''] || 'bg-gray-100 text-gray-800';
}
