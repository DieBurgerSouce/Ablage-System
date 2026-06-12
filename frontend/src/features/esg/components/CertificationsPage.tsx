/**
 * Certifications Page
 *
 * Verwaltung von ESG-Zertifizierungen.
 * Verbunden mit der ESG API via TanStack Query Hooks.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Plus, Download, Filter, Award, Calendar, AlertCircle } from 'lucide-react';
import {
  useCertifications,
  useCertificationSummary,
  useExpiringCertifications,
  getCertificationStatusLabel,
} from '../hooks/use-esg-queries';

export function CertificationsPage() {
  const { data: summary, isLoading: summaryLoading, error: summaryError } = useCertificationSummary();
  const { data: certifications, isLoading: certificationsLoading } = useCertifications({ limit: 50 });
  const { data: expiringCerts } = useExpiringCertifications(90);

  if (summaryError) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>
          Fehler beim Laden der Zertifizierungen: {summaryError.message}
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      {/* Actions */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Zertifizierungen</h2>
          <p className="text-sm text-muted-foreground">
            Verwalten Sie Ihre ESG-Zertifizierungen und deren Gültigkeit
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" disabled title="Kommt bald" aria-label="Zertifikate filtern">
            <Filter className="h-4 w-4 mr-2" />
            Filter
          </Button>
          <Button variant="outline" size="sm" disabled title="Kommt bald" aria-label="Zertifikate exportieren">
            <Download className="h-4 w-4 mr-2" />
            Export
          </Button>
          <Button size="sm" disabled title="Kommt bald" aria-label="Neues Zertifikat hinzufügen">
            <Plus className="h-4 w-4 mr-2" />
            Zertifikat hinzufügen
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Award className="h-4 w-4 text-green-600" />
              Aktive Zertifikate
            </CardTitle>
          </CardHeader>
          <CardContent>
            {summaryLoading ? (
              <Skeleton className="h-8 w-12" />
            ) : (
              <div className="text-2xl font-bold">{summary?.active_count ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Calendar className="h-4 w-4 text-amber-600" />
              Bald ablaufend
            </CardTitle>
          </CardHeader>
          <CardContent>
            {summaryLoading ? (
              <Skeleton className="h-8 w-12" />
            ) : (
              <div className="text-2xl font-bold text-amber-600">
                {expiringCerts?.length ?? summary?.expiring_soon_count ?? 0}
              </div>
            )}
            <p className="text-xs text-muted-foreground">In den nächsten 90 Tagen</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <AlertCircle className="h-4 w-4 text-red-600" />
              Abgelaufen
            </CardTitle>
          </CardHeader>
          <CardContent>
            {summaryLoading ? (
              <Skeleton className="h-8 w-12" />
            ) : (
              <div className="text-2xl font-bold text-red-600">
                {summary?.expired_count ?? 0}
              </div>
            )}
            <p className="text-xs text-muted-foreground">Erneuerung erforderlich</p>
          </CardContent>
        </Card>
      </div>

      {/* Certifications List */}
      <Card>
        <CardHeader>
          <CardTitle>Zertifikats-Übersicht</CardTitle>
          <CardDescription>
            Alle ESG-relevanten Zertifizierungen
          </CardDescription>
        </CardHeader>
        <CardContent>
          {certificationsLoading ? (
            <div className="space-y-4">
              {[...Array(4)].map((_, i) => (
                <Skeleton key={i} className="h-20 w-full" />
              ))}
            </div>
          ) : certifications?.items && certifications.items.length > 0 ? (
            <div className="space-y-4">
              {certifications.items.map((cert) => {
                const statusStyle = getStatusStyle(cert.status);
                return (
                  <div
                    key={cert.id}
                    className={`flex items-center justify-between p-4 border rounded-lg ${statusStyle.borderClass} ${statusStyle.bgClass}`}
                  >
                    <div className="flex items-center gap-4">
                      <div className={`h-10 w-10 rounded-full flex items-center justify-center ${statusStyle.iconBgClass}`}>
                        <Award className={`h-5 w-5 ${statusStyle.iconClass}`} />
                      </div>
                      <div>
                        <p className="font-medium">{cert.certification_name}</p>
                        <p className="text-sm text-muted-foreground">
                          {cert.scope_description || getCategoryLabel(cert.category)}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="text-right">
                        <p className="text-sm text-muted-foreground">
                          {cert.status === 'expired' ? 'Abgelaufen am' : 'Gültig bis'}
                        </p>
                        <p className={`font-medium ${statusStyle.dateClass}`}>
                          {formatDate(cert.expiry_date)}
                        </p>
                      </div>
                      <Badge className={statusStyle.badgeClass}>
                        {getCertificationStatusLabel(cert.status)}
                      </Badge>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              Keine Zertifizierungen vorhanden
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// Helper functions
function formatDate(dateString?: string | null): string {
  if (!dateString) return '-';
  return new Intl.DateTimeFormat('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(dateString));
}

function getCategoryLabel(category?: string): string {
  const labels: Record<string, string> = {
    environmental: 'Umwelt',
    social: 'Soziales',
    governance: 'Unternehmensführung',
  };
  return labels[category ?? ''] || category || '';
}

interface StatusStyle {
  borderClass: string;
  bgClass: string;
  iconBgClass: string;
  iconClass: string;
  dateClass: string;
  badgeClass: string;
}

function getStatusStyle(status?: string): StatusStyle {
  switch (status) {
    case 'active':
      return {
        borderClass: '',
        bgClass: '',
        iconBgClass: 'bg-green-100',
        iconClass: 'text-green-600',
        dateClass: '',
        badgeClass: 'bg-green-600 hover:bg-green-700',
      };
    case 'pending':
      return {
        borderClass: 'border-amber-200',
        bgClass: 'bg-amber-50',
        iconBgClass: 'bg-amber-100',
        iconClass: 'text-amber-600',
        dateClass: 'text-amber-600',
        badgeClass: 'bg-amber-100 text-amber-800 hover:bg-amber-200',
      };
    case 'expired':
      return {
        borderClass: 'border-red-200',
        bgClass: 'bg-red-50',
        iconBgClass: 'bg-red-100',
        iconClass: 'text-red-600',
        dateClass: 'text-red-600',
        badgeClass: 'bg-red-600 hover:bg-red-700',
      };
    case 'revoked':
      return {
        borderClass: 'border-gray-300',
        bgClass: 'bg-gray-50',
        iconBgClass: 'bg-gray-100',
        iconClass: 'text-gray-600',
        dateClass: 'text-gray-600',
        badgeClass: 'bg-gray-600 hover:bg-gray-700',
      };
    default:
      return {
        borderClass: '',
        bgClass: '',
        iconBgClass: 'bg-green-100',
        iconClass: 'text-green-600',
        dateClass: '',
        badgeClass: 'bg-green-600 hover:bg-green-700',
      };
  }
}
