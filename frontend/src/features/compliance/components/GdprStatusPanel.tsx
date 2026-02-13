/**
 * GDPR Status Panel Component
 *
 * Displays GDPR compliance status, issues, and recommendations.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ShieldCheck, XCircle, AlertTriangle, FileText } from 'lucide-react';
import { useRunGdprCheck } from '../hooks/use-compliance-queries';
import type { GdprCheck } from '../types/compliance-types';

interface GdprStatusPanelProps {
  gdprCheck?: GdprCheck;
}

export function GdprStatusPanel({ gdprCheck }: GdprStatusPanelProps) {
  const runGdprCheckMutation = useRunGdprCheck();

  const handleRunCheck = () => {
    runGdprCheckMutation.mutate();
  };

  if (!gdprCheck && !runGdprCheckMutation.data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5" />
            DSGVO-Compliance
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center gap-4 py-8">
            <FileText className="h-12 w-12 text-gray-400" />
            <p className="text-gray-600">Noch keine DSGVO-Prüfung durchgeführt</p>
            <Button onClick={handleRunCheck} disabled={runGdprCheckMutation.isPending}>
              {runGdprCheckMutation.isPending ? 'Wird geprüft...' : 'DSGVO-Prüfung starten'}
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  const data = gdprCheck || runGdprCheckMutation.data;

  if (!data) {
    return null;
  }

  const { compliant, issues, recommendations, personalDataCount, deletionCandidates, details } =
    data;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5" />
            DSGVO-Compliance
          </CardTitle>
          <Badge variant={compliant ? 'default' : 'destructive'} className="gap-1">
            {compliant ? (
              <>
                <ShieldCheck className="h-3 w-3" />
                Konform
              </>
            ) : (
              <>
                <XCircle className="h-3 w-3" />
                Nicht konform
              </>
            )}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Statistics */}
        <div className="grid grid-cols-2 gap-4">
          <div className="p-4 bg-blue-50 rounded-lg">
            <div className="text-2xl font-bold text-blue-900">{personalDataCount}</div>
            <div className="text-sm text-blue-700">Dokumente mit personenbezogenen Daten</div>
          </div>
          <div className="p-4 bg-red-50 rounded-lg">
            <div className="text-2xl font-bold text-red-900">{deletionCandidates}</div>
            <div className="text-sm text-red-700">Löschkandidaten</div>
          </div>
        </div>

        {/* Issues */}
        {issues.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-semibold flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-red-600" />
              Probleme
            </h4>
            <ul className="space-y-1">
              {issues.map((issue, index) => (
                <li key={index} className="text-sm text-red-700 flex items-start gap-2">
                  <span className="text-red-500 mt-0.5">•</span>
                  <span>{issue}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Recommendations */}
        {recommendations.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-semibold">Empfehlungen</h4>
            <ul className="space-y-1">
              {recommendations.map((rec, index) => (
                <li key={index} className="text-sm text-gray-700 flex items-start gap-2">
                  <span className="text-blue-500 mt-0.5">→</span>
                  <span>{rec}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Details */}
        <div className="space-y-2">
          <h4 className="text-sm font-semibold">Detaillierte Prüfung</h4>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <DetailItem label="Datenminimierung" status={details.dataMinimization.status} />
            <DetailItem label="Einwilligungsverwaltung" status={details.consentManagement.status} />
            <DetailItem label="Zugriffsrechte" status={details.accessRights.status} />
            <DetailItem label="Datenportabilität" status={details.dataPortability.status} />
          </div>
        </div>

        {/* Refresh Button */}
        <div className="pt-2">
          <Button
            onClick={handleRunCheck}
            disabled={runGdprCheckMutation.isPending}
            variant="outline"
            size="sm"
            className="w-full"
          >
            {runGdprCheckMutation.isPending ? 'Wird aktualisiert...' : 'Prüfung aktualisieren'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

interface DetailItemProps {
  label: string;
  status: 'compliant' | 'warning' | 'non_compliant' | 'unknown';
}

function DetailItem({ label, status }: DetailItemProps) {
  const color =
    status === 'compliant'
      ? 'text-green-600'
      : status === 'warning'
        ? 'text-yellow-600'
        : 'text-red-600';

  const icon =
    status === 'compliant' ? '✓' : status === 'warning' ? '⚠' : '✗';

  return (
    <div className="flex items-center gap-2">
      <span className={`font-bold ${color}`}>{icon}</span>
      <span className="text-gray-700">{label}</span>
    </div>
  );
}
