/**
 * AnomalyAlerts Component.
 *
 * Zeigt Warnungen bei erkannten Anomalien:
 * - Ungewöhnliche Transaktionen
 * - Abweichende Muster
 * - Potenzielle Probleme
 */

import React, { useState } from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from '@/components/ui/alert';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { AlertTriangle, AlertCircle, Info, CheckCircle, XCircle, Eye, ThumbsDown, ChevronRight } from 'lucide-react';

export type AnomalySeverity = 'info' | 'warning' | 'error' | 'critical';
export type AnomalyStatus = 'new' | 'acknowledged' | 'resolved' | 'false_positive';
export type AnomalyType =
  | 'unusual_amount'
  | 'unusual_frequency'
  | 'unusual_category'
  | 'duplicate_payment'
  | 'missing_payment'
  | 'pattern_deviation'
  | 'budget_exceeded'
  | 'other';

export interface Anomaly {
  id: string;
  type: AnomalyType;
  severity: AnomalySeverity;
  status: AnomalyStatus;
  title: string;
  description: string;
  detectedAt: string;
  entityType: string;
  entityId: string;
  entityName: string;
  amount?: number;
  expectedAmount?: number;
  deviation?: number;
  confidence: number;
  suggestedAction?: string;
  metadata?: Record<string, unknown>;
}

interface AnomalyAlertsProps {
  anomalies: Anomaly[];
  onAcknowledge?: (anomalyId: string) => void;
  onResolve?: (anomalyId: string) => void;
  onMarkFalsePositive?: (anomalyId: string) => void;
  isLoading?: boolean;
}

const formatCurrency = (value: number): string => {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 2,
  }).format(value);
};

const formatDate = (dateStr: string): string => {
  return new Date(dateStr).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const getSeverityIcon = (severity: AnomalySeverity) => {
  switch (severity) {
    case 'critical':
      return <XCircle className="h-5 w-5 text-red-500" />;
    case 'error':
      return <AlertCircle className="h-5 w-5 text-red-400" />;
    case 'warning':
      return <AlertTriangle className="h-5 w-5 text-yellow-500" />;
    case 'info':
      return <Info className="h-5 w-5 text-blue-500" />;
    default:
      return <Info className="h-5 w-5 text-gray-500" />;
  }
};

const getSeverityLabel = (severity: AnomalySeverity): string => {
  switch (severity) {
    case 'critical':
      return 'Kritisch';
    case 'error':
      return 'Fehler';
    case 'warning':
      return 'Warnung';
    case 'info':
      return 'Info';
    default:
      return 'Unbekannt';
  }
};

const getSeverityVariant = (
  severity: AnomalySeverity
): 'default' | 'destructive' | 'outline' | 'secondary' => {
  switch (severity) {
    case 'critical':
    case 'error':
      return 'destructive';
    case 'warning':
      return 'default';
    case 'info':
      return 'secondary';
    default:
      return 'outline';
  }
};

const getStatusLabel = (status: AnomalyStatus): string => {
  switch (status) {
    case 'new':
      return 'Neu';
    case 'acknowledged':
      return 'Bestätigt';
    case 'resolved':
      return 'Gelöst';
    case 'false_positive':
      return 'Fehlalarm';
    default:
      return 'Unbekannt';
  }
};

const getTypeLabel = (type: AnomalyType): string => {
  switch (type) {
    case 'unusual_amount':
      return 'Ungewöhnlicher Betrag';
    case 'unusual_frequency':
      return 'Ungewöhnliche Häufigkeit';
    case 'unusual_category':
      return 'Ungewöhnliche Kategorie';
    case 'duplicate_payment':
      return 'Mögliche Doppelzahlung';
    case 'missing_payment':
      return 'Fehlende Zahlung';
    case 'pattern_deviation':
      return 'Musterabweichung';
    case 'budget_exceeded':
      return 'Budget überschritten';
    case 'other':
      return 'Sonstiges';
    default:
      return 'Unbekannt';
  }
};

const AnomalyDetailDialog: React.FC<{
  anomaly: Anomaly;
  onAcknowledge?: (id: string) => void;
  onResolve?: (id: string) => void;
  onMarkFalsePositive?: (id: string) => void;
}> = ({ anomaly, onAcknowledge, onResolve, onMarkFalsePositive }) => {
  return (
    <DialogContent className="max-w-lg">
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2">
          {getSeverityIcon(anomaly.severity)}
          {anomaly.title}
        </DialogTitle>
        <DialogDescription>
          Erkannt am {formatDate(anomaly.detectedAt)}
        </DialogDescription>
      </DialogHeader>

      <div className="space-y-4">
        <div>
          <h4 className="text-sm font-medium mb-1">Beschreibung</h4>
          <p className="text-sm text-muted-foreground">{anomaly.description}</p>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <h4 className="text-sm font-medium mb-1">Typ</h4>
            <Badge variant="outline">{getTypeLabel(anomaly.type)}</Badge>
          </div>
          <div>
            <h4 className="text-sm font-medium mb-1">Status</h4>
            <Badge variant="outline">{getStatusLabel(anomaly.status)}</Badge>
          </div>
        </div>

        {anomaly.amount !== undefined && (
          <div className="grid grid-cols-2 gap-4">
            <div>
              <h4 className="text-sm font-medium mb-1">Betrag</h4>
              <p className="text-lg font-bold">{formatCurrency(anomaly.amount)}</p>
            </div>
            {anomaly.expectedAmount !== undefined && (
              <div>
                <h4 className="text-sm font-medium mb-1">Erwartet</h4>
                <p className="text-lg">{formatCurrency(anomaly.expectedAmount)}</p>
              </div>
            )}
          </div>
        )}

        {anomaly.deviation !== undefined && (
          <div>
            <h4 className="text-sm font-medium mb-1">Abweichung</h4>
            <p className={`text-lg font-bold ${
              anomaly.deviation > 0 ? 'text-red-500' : 'text-green-500'
            }`}>
              {anomaly.deviation > 0 ? '+' : ''}{anomaly.deviation.toFixed(1)}%
            </p>
          </div>
        )}

        <div>
          <h4 className="text-sm font-medium mb-1">Betroffene Entität</h4>
          <p className="text-sm text-muted-foreground">
            {anomaly.entityType}: {anomaly.entityName}
          </p>
        </div>

        <div>
          <h4 className="text-sm font-medium mb-1">Konfidenz</h4>
          <div className="flex items-center gap-2">
            <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
              <div
                className="h-full bg-primary"
                style={{ width: `${anomaly.confidence * 100}%` }}
              />
            </div>
            <span className="text-sm">{Math.round(anomaly.confidence * 100)}%</span>
          </div>
        </div>

        {anomaly.suggestedAction && (
          <Alert>
            <Info className="h-4 w-4" />
            <AlertTitle>Empfohlene Aktion</AlertTitle>
            <AlertDescription>{anomaly.suggestedAction}</AlertDescription>
          </Alert>
        )}
      </div>

      <DialogFooter className="flex-col sm:flex-row gap-2">
        {anomaly.status === 'new' && (
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onMarkFalsePositive?.(anomaly.id)}
            >
              <ThumbsDown className="h-4 w-4 mr-1" />
              Fehlalarm
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => onAcknowledge?.(anomaly.id)}
            >
              <Eye className="h-4 w-4 mr-1" />
              Zur Kenntnis nehmen
            </Button>
            <Button
              size="sm"
              onClick={() => onResolve?.(anomaly.id)}
            >
              <CheckCircle className="h-4 w-4 mr-1" />
              Als gelöst markieren
            </Button>
          </>
        )}
        {anomaly.status === 'acknowledged' && (
          <Button
            size="sm"
            onClick={() => onResolve?.(anomaly.id)}
          >
            <CheckCircle className="h-4 w-4 mr-1" />
            Als gelöst markieren
          </Button>
        )}
      </DialogFooter>
    </DialogContent>
  );
};

export const AnomalyAlerts: React.FC<AnomalyAlertsProps> = ({
  anomalies,
  onAcknowledge,
  onResolve,
  onMarkFalsePositive,
  isLoading = false,
}) => {
  const [selectedAnomaly, setSelectedAnomaly] = useState<Anomaly | null>(null);

  // Gruppiere nach Status
  const newAnomalies = anomalies.filter((a) => a.status === 'new');
  const acknowledgedAnomalies = anomalies.filter((a) => a.status === 'acknowledged');
  const resolvedAnomalies = anomalies.filter(
    (a) => a.status === 'resolved' || a.status === 'false_positive'
  );

  // Sortiere nach Schweregrad
  const sortBySeverity = (a: Anomaly, b: Anomaly) => {
    const order: Record<AnomalySeverity, number> = {
      critical: 0,
      error: 1,
      warning: 2,
      info: 3,
    };
    return order[a.severity] - order[b.severity];
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-32" />
          <Skeleton className="h-4 w-48" />
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {[...Array(3)].map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5" />
              Anomalie-Warnungen
            </CardTitle>
            <CardDescription>
              Erkannte Unregelmäßigkeiten in Ihren Finanzdaten
            </CardDescription>
          </div>
          {newAnomalies.length > 0 && (
            <Badge variant="destructive">
              {newAnomalies.length} Neu
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {anomalies.length === 0 ? (
          <div className="text-center py-8">
            <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-3" />
            <p className="text-lg font-medium">Keine Anomalien erkannt</p>
            <p className="text-sm text-muted-foreground">
              Alle Transaktionen entsprechen den erwarteten Mustern
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Neue Anomalien */}
            {newAnomalies.length > 0 && (
              <div>
                <h3 className="text-sm font-medium mb-3 text-muted-foreground">
                  Neue Warnungen ({newAnomalies.length})
                </h3>
                <div className="space-y-2">
                  {newAnomalies.sort(sortBySeverity).map((anomaly) => (
                    <Dialog key={anomaly.id}>
                      <DialogTrigger asChild>
                        <div
                          className="flex items-center gap-3 p-3 rounded-lg border cursor-pointer hover:bg-muted/50 transition-colors"
                          onClick={() => setSelectedAnomaly(anomaly)}
                        >
                          {getSeverityIcon(anomaly.severity)}
                          <div className="flex-1 min-w-0">
                            <p className="font-medium truncate">{anomaly.title}</p>
                            <p className="text-sm text-muted-foreground truncate">
                              {anomaly.description}
                            </p>
                          </div>
                          <div className="flex items-center gap-2">
                            <Badge variant={getSeverityVariant(anomaly.severity)}>
                              {getSeverityLabel(anomaly.severity)}
                            </Badge>
                            <ChevronRight className="h-4 w-4 text-muted-foreground" />
                          </div>
                        </div>
                      </DialogTrigger>
                      <AnomalyDetailDialog
                        anomaly={anomaly}
                        onAcknowledge={onAcknowledge}
                        onResolve={onResolve}
                        onMarkFalsePositive={onMarkFalsePositive}
                      />
                    </Dialog>
                  ))}
                </div>
              </div>
            )}

            {/* Bestätigte Anomalien */}
            {acknowledgedAnomalies.length > 0 && (
              <div>
                <h3 className="text-sm font-medium mb-3 text-muted-foreground">
                  In Bearbeitung ({acknowledgedAnomalies.length})
                </h3>
                <div className="space-y-2">
                  {acknowledgedAnomalies.sort(sortBySeverity).map((anomaly) => (
                    <Dialog key={anomaly.id}>
                      <DialogTrigger asChild>
                        <div
                          className="flex items-center gap-3 p-3 rounded-lg border border-dashed cursor-pointer hover:bg-muted/50 transition-colors opacity-75"
                          onClick={() => setSelectedAnomaly(anomaly)}
                        >
                          {getSeverityIcon(anomaly.severity)}
                          <div className="flex-1 min-w-0">
                            <p className="font-medium truncate">{anomaly.title}</p>
                            <p className="text-sm text-muted-foreground truncate">
                              {anomaly.entityName}
                            </p>
                          </div>
                          <Badge variant="outline">
                            {getStatusLabel(anomaly.status)}
                          </Badge>
                        </div>
                      </DialogTrigger>
                      <AnomalyDetailDialog
                        anomaly={anomaly}
                        onAcknowledge={onAcknowledge}
                        onResolve={onResolve}
                        onMarkFalsePositive={onMarkFalsePositive}
                      />
                    </Dialog>
                  ))}
                </div>
              </div>
            )}

            {/* Gelöste Anomalien (collapsed) */}
            {resolvedAnomalies.length > 0 && (
              <details className="group">
                <summary className="text-sm font-medium text-muted-foreground cursor-pointer list-none">
                  <div className="flex items-center gap-2">
                    <ChevronRight className="h-4 w-4 transition-transform group-open:rotate-90" />
                    Gelöst ({resolvedAnomalies.length})
                  </div>
                </summary>
                <div className="mt-3 space-y-2">
                  {resolvedAnomalies.slice(0, 5).map((anomaly) => (
                    <div
                      key={anomaly.id}
                      className="flex items-center gap-3 p-2 rounded-lg bg-muted/30 opacity-50"
                    >
                      <CheckCircle className="h-4 w-4 text-green-500" />
                      <span className="text-sm truncate">{anomaly.title}</span>
                      <Badge variant="outline" className="ml-auto text-xs">
                        {getStatusLabel(anomaly.status)}
                      </Badge>
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default AnomalyAlerts;
