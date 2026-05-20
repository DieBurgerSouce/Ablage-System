/**
 * Audit Trail Card Component
 *
 * Displays audit chain health and statistics.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { FileText, ShieldCheck, AlertTriangle, CheckCircle } from 'lucide-react';
import { useVerifyAuditChain } from '../hooks/use-compliance-queries';
import { toast } from 'sonner';
import type { AuditChainStats } from '../types/compliance-types';

interface AuditTrailCardProps {
  stats: AuditChainStats;
}

export function AuditTrailCard({ stats }: AuditTrailCardProps) {
  const verifyChainMutation = useVerifyAuditChain();

  const {
    totalEntries,
    entriesLast24h,
    entriesLast7d,
    unverifiedEntries,
    chainIntegrity,
    lastVerification,
    eventsByType,
  } = stats;

  const handleVerifyChain = async () => {
    try {
      const result = await verifyChainMutation.mutateAsync();
      if (result.valid) {
        toast.success('Audit-Kette erfolgreich verifiziert', {
          description: result.message,
        });
      } else {
        toast.error('Audit-Kette hat Integritätsprobleme', {
          description: result.message,
        });
      }
    } catch (error) {
      toast.error('Fehler bei der Verifizierung', {
        description: 'Die Audit-Kette konnte nicht verifiziert werden',
      });
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            Audit-Trail
          </CardTitle>
          <Badge variant={chainIntegrity ? 'default' : 'destructive'} className="gap-1">
            {chainIntegrity ? (
              <>
                <CheckCircle className="h-3 w-3" />
                Integrität OK
              </>
            ) : (
              <>
                <AlertTriangle className="h-3 w-3" />
                Probleme
              </>
            )}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Summary Stats */}
        <div className="grid grid-cols-3 gap-4">
          <div className="p-3 bg-blue-50 rounded-lg">
            <div className="text-2xl font-bold text-blue-900">{totalEntries}</div>
            <div className="text-xs text-blue-700">Gesamt-Einträge</div>
          </div>
          <div className="p-3 bg-green-50 rounded-lg">
            <div className="text-2xl font-bold text-green-900">{entriesLast24h}</div>
            <div className="text-xs text-green-700">Letzte 24h</div>
          </div>
          <div className="p-3 bg-purple-50 rounded-lg">
            <div className="text-2xl font-bold text-purple-900">{entriesLast7d}</div>
            <div className="text-xs text-purple-700">Letzte 7 Tage</div>
          </div>
        </div>

        {/* Unverified Entries Warning */}
        {unverifiedEntries > 0 && (
          <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-lg flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-yellow-600 mt-0.5" />
            <div className="flex-1">
              <div className="font-semibold text-yellow-900">
                {unverifiedEntries} unverifizierte Einträge
              </div>
              <div className="text-sm text-yellow-700">
                Diese Einträge sollten verifiziert werden, um die Integrität sicherzustellen.
              </div>
            </div>
          </div>
        )}

        {/* Last Verification */}
        <div className="text-sm text-gray-600">
          Letzte Verifizierung:{' '}
          <span className="font-semibold text-gray-900">
            {lastVerification.toLocaleString('de-DE', {
              dateStyle: 'medium',
              timeStyle: 'short',
            })}
          </span>
        </div>

        {/* Events by Type */}
        <div className="space-y-2">
          <h4 className="text-sm font-semibold text-gray-700">Ereignisse nach Typ</h4>
          <div className="grid grid-cols-2 gap-2 text-sm">
            {Object.entries(eventsByType)
              .filter(([, count]) => count > 0)
              .sort(([, a], [, b]) => b - a)
              .map(([type, count]) => (
                <EventTypeItem key={type} type={type} count={count} />
              ))}
          </div>
        </div>

        {/* Verify Button */}
        <Button
          onClick={handleVerifyChain}
          disabled={verifyChainMutation.isPending}
          className="w-full gap-2"
          variant={chainIntegrity ? 'outline' : 'default'}
        >
          <ShieldCheck className="h-4 w-4" />
          {verifyChainMutation.isPending ? 'Wird verifiziert...' : 'Kette verifizieren'}
        </Button>
      </CardContent>
    </Card>
  );
}

interface EventTypeItemProps {
  type: string;
  count: number;
}

function EventTypeItem({ type, count }: EventTypeItemProps) {
  const labels: Record<string, string> = {
    create: 'Erstellt',
    read: 'Gelesen',
    update: 'Aktualisiert',
    delete: 'Gelöscht',
    archive: 'Archiviert',
    restore: 'Wiederhergestellt',
    share: 'Geteilt',
    export: 'Exportiert',
  };

  return (
    <div className="flex items-center justify-between p-2 bg-gray-50 rounded">
      <span className="text-gray-700">{labels[type] || type}</span>
      <Badge variant="outline" className="font-semibold">
        {count}
      </Badge>
    </div>
  );
}
