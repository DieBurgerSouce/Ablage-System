/**
 * External Sources Card Component
 *
 * Zeigt Status der externen Datenquellen-Pruefung.
 */

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Globe,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Clock,
  ExternalLink,
  Building,
  FileWarning,
  CreditCard,
  Shield,
} from 'lucide-react';
import type { ExternalSourceCheck } from '../api/risk-intelligence-api';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';

interface ExternalSourcesCardProps {
  externalCheck: ExternalSourceCheck;
  className?: string;
}

export function ExternalSourcesCard({ externalCheck, className }: ExternalSourcesCardProps) {
  const getSourceIcon = (source: string) => {
    switch (source.toLowerCase()) {
      case 'creditreform':
        return <CreditCard className="w-4 h-4" />;
      case 'schufa':
        return <Shield className="w-4 h-4" />;
      case 'insolvency_register':
      case 'insolvenzregister':
        return <FileWarning className="w-4 h-4" />;
      case 'handelsregister':
        return <Building className="w-4 h-4" />;
      default:
        return <Globe className="w-4 h-4" />;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'checked':
        return (
          <Badge variant="default" className="gap-1">
            <CheckCircle className="w-3 h-3" />
            Geprueft
          </Badge>
        );
      case 'not_configured':
        return (
          <Badge variant="secondary" className="gap-1">
            <Clock className="w-3 h-3" />
            Nicht konfiguriert
          </Badge>
        );
      case 'error':
        return (
          <Badge variant="destructive" className="gap-1">
            <XCircle className="w-3 h-3" />
            Fehler
          </Badge>
        );
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  };

  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case 'critical':
        return <XCircle className="w-4 h-4 text-red-500" />;
      case 'warning':
        return <AlertTriangle className="w-4 h-4 text-orange-500" />;
      case 'info':
        return <CheckCircle className="w-4 h-4 text-blue-500" />;
      default:
        return null;
    }
  };

  const criticalAlerts = externalCheck.alerts.filter((a) => a.severity === 'critical');
  const warningAlerts = externalCheck.alerts.filter((a) => a.severity === 'warning');

  return (
    <Card className={className}>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Globe className="w-5 h-5 text-muted-foreground" />
            <div>
              <CardTitle className="text-lg">Externe Quellen</CardTitle>
              <CardDescription>
                Zuletzt geprueft:{' '}
                {format(new Date(externalCheck.last_checked), 'dd. MMM yyyy, HH:mm', { locale: de })}
              </CardDescription>
            </div>
          </div>
          {externalCheck.alerts.length > 0 && (
            <Badge variant={criticalAlerts.length > 0 ? 'destructive' : 'secondary'}>
              {externalCheck.alerts.length} Alert{externalCheck.alerts.length !== 1 ? 's' : ''}
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {/* Alerts */}
        {externalCheck.alerts.length > 0 && (
          <div className="space-y-3 mb-6">
            {criticalAlerts.length > 0 && (
              <Alert variant="destructive">
                <XCircle className="w-4 h-4" />
                <AlertTitle>Kritische Warnungen</AlertTitle>
                <AlertDescription>
                  <ul className="mt-2 space-y-1">
                    {criticalAlerts.map((alert, index) => (
                      <li key={index} className="text-sm">
                        <strong>{alert.source}:</strong> {alert.message}
                      </li>
                    ))}
                  </ul>
                </AlertDescription>
              </Alert>
            )}
            {warningAlerts.length > 0 && (
              <Alert>
                <AlertTriangle className="w-4 h-4" />
                <AlertTitle>Warnungen</AlertTitle>
                <AlertDescription>
                  <ul className="mt-2 space-y-1">
                    {warningAlerts.map((alert, index) => (
                      <li key={index} className="text-sm">
                        <strong>{alert.source}:</strong> {alert.message}
                      </li>
                    ))}
                  </ul>
                </AlertDescription>
              </Alert>
            )}
          </div>
        )}

        {/* Sources List */}
        <div className="space-y-3">
          <p className="text-sm font-medium text-muted-foreground">Geprueft Quellen</p>
          <ScrollArea className="h-48">
            <div className="space-y-2">
              {externalCheck.sources_checked.map((source, index) => (
                <div
                  key={index}
                  className="flex items-center justify-between p-3 border rounded-lg"
                >
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-muted rounded-full">
                      {getSourceIcon(source.source)}
                    </div>
                    <div>
                      <p className="font-medium">{source.name}</p>
                      {source.last_checked && (
                        <p className="text-xs text-muted-foreground">
                          {format(new Date(source.last_checked), 'dd.MM.yyyy HH:mm', { locale: de })}
                        </p>
                      )}
                    </div>
                  </div>
                  {getStatusBadge(source.status)}
                </div>
              ))}
            </div>
          </ScrollArea>
        </div>

        {/* Info */}
        <div className="mt-4 p-3 bg-muted rounded-lg">
          <p className="text-sm text-muted-foreground">
            <ExternalLink className="w-4 h-4 inline mr-1" />
            Externe Quellen werden automatisch geprueft, wenn konfiguriert.
            Creditreform und SCHUFA erfordern eine separate API-Konfiguration.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
