/**
 * Network Graph Component
 *
 * Visualisiert Netzwerk-Verbindungen zwischen Entities.
 */

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Network, AlertTriangle, Link2, MapPin, CreditCard, ShieldAlert } from 'lucide-react';
import type { NetworkAnalysis, NetworkConnection } from '../api/risk-intelligence-api';

interface NetworkGraphProps {
  network: NetworkAnalysis;
  className?: string;
}

export function NetworkGraph({ network, className }: NetworkGraphProps) {
  const getConnectionIcon = (type: NetworkConnection['connection_type']) => {
    switch (type) {
      case 'shared_iban':
        return <CreditCard className="w-4 h-4" />;
      case 'shared_address':
        return <MapPin className="w-4 h-4" />;
      default:
        return <Link2 className="w-4 h-4" />;
    }
  };

  const getConnectionLabel = (type: NetworkConnection['connection_type']) => {
    switch (type) {
      case 'shared_iban':
        return 'Gleiche IBAN';
      case 'shared_address':
        return 'Gleiche Adresse';
      default:
        return 'Verbindung';
    }
  };

  const getRiskBadge = (indicator: NetworkConnection['risk_indicator']) => {
    const variants: Record<string, { variant: 'default' | 'secondary' | 'destructive'; label: string }> = {
      high: { variant: 'destructive', label: 'Hoch' },
      medium: { variant: 'secondary', label: 'Mittel' },
      low: { variant: 'default', label: 'Niedrig' },
    };
    const { variant, label } = variants[indicator] || variants.low;
    return <Badge variant={variant} className="text-xs">{label}</Badge>;
  };

  return (
    <Card className={className}>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Network className="w-5 h-5 text-muted-foreground" />
            <div>
              <CardTitle className="text-lg">Netzwerk-Analyse</CardTitle>
              <CardDescription>
                {network.connection_count} Verbindung{network.connection_count !== 1 ? 'en' : ''} gefunden
              </CardDescription>
            </div>
          </div>
          <div className="text-right">
            <p className="text-sm text-muted-foreground">Netzwerk-Score</p>
            <p className="text-xl font-bold">{network.network_risk_score.toFixed(0)}</p>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {network.has_suspicious_connections && (
          <Alert variant="destructive" className="mb-4">
            <ShieldAlert className="w-4 h-4" />
            <AlertTitle>Verdaechtige Verbindungen</AlertTitle>
            <AlertDescription>
              Es wurden potenziell verdaechtige Verbindungen zu anderen Entities gefunden.
              Eine manuelle Pruefung wird empfohlen.
            </AlertDescription>
          </Alert>
        )}

        {network.connections.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <Network className="w-12 h-12 mx-auto mb-2 opacity-50" />
            <p>Keine Netzwerk-Verbindungen gefunden</p>
            <p className="text-sm">Die Entity hat keine erkennbaren Verbindungen zu anderen Entities.</p>
          </div>
        ) : (
          <ScrollArea className="h-64">
            <div className="space-y-3">
              {network.connections.map((connection, index) => (
                <div
                  key={index}
                  className="flex items-start gap-3 p-3 border rounded-lg hover:bg-muted/50 transition-colors"
                >
                  <div className="p-2 bg-muted rounded-full">
                    {getConnectionIcon(connection.connection_type)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="font-medium truncate">{connection.entity_name}</p>
                      {getRiskBadge(connection.risk_indicator)}
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {getConnectionLabel(connection.connection_type)}
                    </p>
                    {connection.details && (
                      <p className="text-xs text-muted-foreground mt-1">{connection.details}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        )}

        {/* Risk Distribution */}
        {network.connections.length > 0 && (
          <div className="mt-4 pt-4 border-t">
            <p className="text-sm text-muted-foreground mb-2">Risiko-Verteilung</p>
            <div className="flex gap-2">
              {(['high', 'medium', 'low'] as const).map((level) => {
                const count = network.connections.filter((c) => c.risk_indicator === level).length;
                if (count === 0) return null;
                return (
                  <Badge
                    key={level}
                    variant={level === 'high' ? 'destructive' : level === 'medium' ? 'secondary' : 'default'}
                  >
                    {level === 'high' ? 'Hoch' : level === 'medium' ? 'Mittel' : 'Niedrig'}: {count}
                  </Badge>
                );
              })}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
