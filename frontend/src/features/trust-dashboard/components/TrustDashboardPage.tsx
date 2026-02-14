/**
 * Trust Dashboard - Security & Compliance Monitoring
 *
 * Überwacht Sicherheitsereignisse, Anomalien und Compliance-Status.
 * Zeigt Zugriffsprotokolle, Export-Aktivitäten und erkannte Anomalien.
 */

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Progress } from '@/components/ui/progress';
import { useTrustDashboard, useAccessLog, useAnomalies } from '../hooks/use-trust-dashboard';
import {
  Shield,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Eye,
  Download,
  Users,
  Activity,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';

export function TrustDashboardPage() {
  const [days, setDays] = useState(30);
  const [accessLogPage, setAccessLogPage] = useState(0);
  const pageSize = 20;

  const { data: snapshot, isLoading, error, isRefetching } = useTrustDashboard(days);
  const {
    data: accessLog,
    isLoading: accessLogLoading,
  } = useAccessLog(days, pageSize, accessLogPage * pageSize);
  const { data: anomalies, isLoading: anomaliesLoading } = useAnomalies(7, 50);

  if (isLoading) {
    return <DashboardSkeleton />;
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="h-4 w-4" />
        <AlertDescription>
          Fehler beim Laden des Trust Dashboard. Bitte versuchen Sie es später erneut.
        </AlertDescription>
      </Alert>
    );
  }

  if (!snapshot) {
    return null;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight font-display">Trust Dashboard</h2>
          <p className="text-muted-foreground mt-1">
            Sicherheitsüberwachung und Compliance-Monitoring
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Zeitraum-Filter */}
          <div className="flex gap-2">
            {[7, 30, 90].map((d) => (
              <Button
                key={d}
                variant={days === d ? 'default' : 'outline'}
                size="sm"
                onClick={() => setDays(d)}
              >
                {d} Tage
              </Button>
            ))}
          </div>
          {isRefetching && (
            <Badge variant="outline" className="animate-pulse">
              <Activity className="mr-2 h-3 w-3" />
              Aktualisierung...
            </Badge>
          )}
        </div>
      </div>

      {/* Metriken-Übersicht */}
      <div className="grid gap-4 md:grid-cols-5">
        <MetricCard
          title="Gesamtzugriffe"
          value={snapshot.metrics.total_accesses}
          icon={<Eye className="h-4 w-4" />}
        />
        <MetricCard
          title="Sensible Zugriffe"
          value={snapshot.metrics.sensitive_accesses}
          icon={<Shield className="h-4 w-4" />}
          variant={snapshot.metrics.sensitive_accesses > 0 ? 'warning' : 'default'}
        />
        <MetricCard
          title="Exporte"
          value={snapshot.metrics.export_count}
          icon={<Download className="h-4 w-4" />}
        />
        <MetricCard
          title="Anomalien"
          value={snapshot.metrics.anomaly_count}
          icon={<AlertTriangle className="h-4 w-4" />}
          variant={snapshot.metrics.anomaly_count > 0 ? 'danger' : 'default'}
        />
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Compliance-Score</CardTitle>
            <Shield className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="text-2xl font-bold">{snapshot.metrics.compliance_score}/100</div>
              <Progress value={snapshot.metrics.compliance_score} className="h-2" />
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Sicherheitsereignisse */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5" />
              Aktuelle Sicherheitsereignisse
            </CardTitle>
          </CardHeader>
          <CardContent>
            {accessLogLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-16 w-full" />
                ))}
              </div>
            ) : accessLog && accessLog.events.length > 0 ? (
              <div className="space-y-2">
                <div className="rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Aktion</TableHead>
                        <TableHead>Ressource</TableHead>
                        <TableHead>IP-Adresse</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Zeit</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {accessLog.events.slice(0, 5).map((event) => (
                        <TableRow key={event.id}>
                          <TableCell className="font-medium">{event.action}</TableCell>
                          <TableCell className="text-sm">
                            {event.resource_type && event.resource_id ? (
                              <span>
                                {event.resource_type}
                                <span className="text-muted-foreground">
                                  :{event.resource_id.slice(0, 8)}
                                </span>
                              </span>
                            ) : (
                              <span className="text-muted-foreground">-</span>
                            )}
                          </TableCell>
                          <TableCell className="text-sm">
                            {event.ip_address || '-'}
                          </TableCell>
                          <TableCell>
                            {event.success ? (
                              <CheckCircle2 className="h-4 w-4 text-green-600" />
                            ) : (
                              <XCircle className="h-4 w-4 text-red-600" />
                            )}
                          </TableCell>
                          <TableCell className="text-sm text-muted-foreground">
                            {new Date(event.created_at).toLocaleString('de-DE')}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
                {/* Pagination */}
                {accessLog.total > pageSize && (
                  <div className="flex items-center justify-between pt-2">
                    <div className="text-sm text-muted-foreground">
                      Zeige {accessLogPage * pageSize + 1}-
                      {Math.min((accessLogPage + 1) * pageSize, accessLog.total)} von{' '}
                      {accessLog.total}
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setAccessLogPage((p) => Math.max(0, p - 1))}
                        disabled={accessLogPage === 0}
                      >
                        <ChevronLeft className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setAccessLogPage((p) => p + 1)}
                        disabled={(accessLogPage + 1) * pageSize >= accessLog.total}
                      >
                        <ChevronRight className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground text-center py-8">
                Keine Ereignisse gefunden
              </p>
            )}
          </CardContent>
        </Card>

        {/* Anomalien */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5" />
              Erkannte Anomalien (7 Tage)
            </CardTitle>
          </CardHeader>
          <CardContent>
            {anomaliesLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-20 w-full" />
                ))}
              </div>
            ) : anomalies && anomalies.anomalies.length > 0 ? (
              <div className="space-y-3">
                {anomalies.anomalies.slice(0, 8).map((anomaly) => (
                  <div
                    key={anomaly.id}
                    className="flex items-start justify-between p-3 rounded-lg border"
                  >
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center gap-2">
                        <Badge variant={getSeverityVariant(anomaly.severity)}>
                          {getSeverityLabel(anomaly.severity)}
                        </Badge>
                        <span className="text-sm font-medium">{anomaly.type}</span>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        Aktion: {anomaly.action}
                      </p>
                      {anomaly.error_message && (
                        <p className="text-xs text-muted-foreground">
                          {anomaly.error_message}
                        </p>
                      )}
                      <p className="text-xs text-muted-foreground">
                        IP: {anomaly.ip_address || 'Unbekannt'} •{' '}
                        {new Date(anomaly.created_at).toLocaleString('de-DE')}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8">
                <CheckCircle2 className="h-12 w-12 text-green-600 mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">
                  Keine Anomalien erkannt - Alles sicher!
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Top Dokumente */}
      {snapshot.top_documents.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Eye className="h-5 w-5" />
              Meistabgerufene Dokumente
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {snapshot.top_documents.map((doc) => (
                <div
                  key={doc.document_id}
                  className="flex items-center justify-between p-3 rounded-lg border"
                >
                  <span className="text-sm font-medium truncate flex-1">
                    {doc.filename}
                  </span>
                  <Badge variant="secondary">{doc.access_count} Zugriffe</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* User-Aktivität */}
      {snapshot.user_activity.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-5 w-5" />
              Aktivste Benutzer
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {snapshot.user_activity.map((user) => (
                <div
                  key={user.user_id}
                  className="flex items-center justify-between p-3 rounded-lg border"
                >
                  <span className="text-sm font-medium">{user.username}</span>
                  <Badge variant="secondary">{user.action_count} Aktionen</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ==================== Helper Components ====================

interface MetricCardProps {
  title: string;
  value: number;
  icon: React.ReactNode;
  variant?: 'default' | 'warning' | 'danger';
}

function MetricCard({ title, value, icon, variant = 'default' }: MetricCardProps) {
  const getVariantClass = () => {
    switch (variant) {
      case 'warning':
        return 'border-yellow-500';
      case 'danger':
        return 'border-red-500';
      default:
        return '';
    }
  };

  return (
    <Card className={getVariantClass()}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        {icon}
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value.toLocaleString('de-DE')}</div>
      </CardContent>
    </Card>
  );
}

function getSeverityVariant(
  severity: string
): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (severity) {
    case 'critical':
      return 'destructive';
    case 'high':
      return 'destructive';
    case 'medium':
      return 'secondary';
    default:
      return 'outline';
  }
}

function getSeverityLabel(severity: string): string {
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
      return severity;
  }
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div>
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-96 mt-2" />
      </div>
      <div className="grid gap-4 md:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <Card key={i}>
            <CardHeader>
              <Skeleton className="h-4 w-24" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-16" />
            </CardContent>
          </Card>
        ))}
      </div>
      <div className="grid gap-6 md:grid-cols-2">
        {Array.from({ length: 2 }).map((_, i) => (
          <Card key={i}>
            <CardHeader>
              <Skeleton className="h-6 w-48" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-64 w-full" />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
