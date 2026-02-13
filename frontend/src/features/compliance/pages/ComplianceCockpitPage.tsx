/**
 * Compliance Cockpit Page
 *
 * Main dashboard for GoBD, GDPR, retention, and audit compliance.
 */

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { RefreshCw, Play, Download, AlertCircle, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import {
  useComplianceReport,
  useRetentionStats,
  useAuditChainStats,
  useRunComplianceScan,
  useDownloadAuditPackage,
} from '../hooks/use-compliance-queries';
import { ComplianceScoreCard } from '../components/ComplianceScoreCard';
import { GdprStatusPanel } from '../components/GdprStatusPanel';
import { RetentionDashboard } from '../components/RetentionDashboard';
import { AuditTrailCard } from '../components/AuditTrailCard';
import { ComplianceScanResults } from '../components/ComplianceScanResults';
import type { ComplianceScanResult } from '../types/compliance-types';

export function ComplianceCockpitPage() {
  const [scanResult, setScanResult] = useState<ComplianceScanResult | null>(null);

  // Queries
  const {
    data: report,
    isLoading: reportLoading,
    error: reportError,
    refetch: refetchReport,
  } = useComplianceReport();

  const {
    data: retentionStats,
    isLoading: retentionLoading,
    error: retentionError,
  } = useRetentionStats();

  const {
    data: auditStats,
    isLoading: auditLoading,
    error: auditError,
  } = useAuditChainStats();

  // Mutations
  const runScanMutation = useRunComplianceScan();
  const downloadAuditPackageMutation = useDownloadAuditPackage();

  const isLoading = reportLoading || retentionLoading || auditLoading;
  const hasError = reportError || retentionError || auditError;

  const handleRunScan = async () => {
    try {
      const result = await runScanMutation.mutateAsync();
      setScanResult(result);
      toast.success('Compliance-Scan abgeschlossen', {
        description: `${result.passed} von ${result.totalChecks} Prüfungen bestanden`,
      });
    } catch (error) {
      toast.error('Fehler beim Compliance-Scan', {
        description: 'Der Scan konnte nicht durchgeführt werden',
      });
    }
  };

  const handleDownloadAuditPackage = async () => {
    try {
      await downloadAuditPackageMutation.mutateAsync();
      toast.success('Audit-Paket heruntergeladen', {
        description: 'Das ZIP-Archiv wurde erfolgreich erstellt',
      });
    } catch (error) {
      toast.error('Fehler beim Download', {
        description: 'Das Audit-Paket konnte nicht erstellt werden',
      });
    }
  };

  const handleRefresh = () => {
    refetchReport();
    toast.info('Daten werden aktualisiert...');
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="container mx-auto p-6">
        <div className="flex items-center justify-center min-h-[400px]">
          <div className="flex flex-col items-center gap-4">
            <Loader2 className="h-12 w-12 animate-spin text-blue-600" />
            <p className="text-gray-600">Compliance-Daten werden geladen...</p>
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (hasError || !report || !retentionStats || !auditStats) {
    return (
      <div className="container mx-auto p-6">
        <Card className="border-red-200 bg-red-50">
          <CardContent className="flex items-center gap-4 p-6">
            <AlertCircle className="h-8 w-8 text-red-600 flex-shrink-0" />
            <div className="flex-1">
              <h3 className="text-lg font-semibold text-red-900 mb-1">
                Fehler beim Laden der Compliance-Daten
              </h3>
              <p className="text-red-700">
                {reportError?.message ||
                  retentionError?.message ||
                  auditError?.message ||
                  'Ein unbekannter Fehler ist aufgetreten'}
              </p>
            </div>
            <Button onClick={handleRefresh} variant="outline">
              <RefreshCw className="h-4 w-4 mr-2" />
              Erneut versuchen
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Compliance Cockpit</h1>
          <p className="text-gray-600 mt-1">
            GoBD, DSGVO, Aufbewahrungsfristen und Audit-Trail
          </p>
        </div>
        <div className="flex gap-2">
          <Button onClick={handleRefresh} variant="outline" size="sm" disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Aktualisieren
          </Button>
          <Button
            onClick={handleRunScan}
            disabled={runScanMutation.isPending}
            size="sm"
            variant="default"
          >
            {runScanMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Scan läuft...
              </>
            ) : (
              <>
                <Play className="h-4 w-4 mr-2" />
                Compliance-Scan starten
              </>
            )}
          </Button>
          <Button
            onClick={handleDownloadAuditPackage}
            disabled={downloadAuditPackageMutation.isPending}
            size="sm"
            variant="outline"
          >
            {downloadAuditPackageMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Erstelle Paket...
              </>
            ) : (
              <>
                <Download className="h-4 w-4 mr-2" />
                Audit-Paket
              </>
            )}
          </Button>
        </div>
      </div>

      {/* Top Row: Compliance Score */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <ComplianceScoreCard report={report} />
      </div>

      {/* Middle Row: GDPR + Retention */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <GdprStatusPanel />
        <RetentionDashboard stats={retentionStats} />
      </div>

      {/* Bottom Row: Audit Trail + Scan Results */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <AuditTrailCard stats={auditStats} />
        <ComplianceScanResults scanResult={scanResult} />
      </div>

      {/* Recommendations Section */}
      {report.recommendations.length > 0 && (
        <Card>
          <CardContent className="p-6">
            <h3 className="text-lg font-semibold mb-4">Empfehlungen</h3>
            <ul className="space-y-2">
              {report.recommendations.map((rec, index) => (
                <li key={index} className="flex items-start gap-3 text-sm">
                  <span className="text-blue-500 mt-1">→</span>
                  <span className="text-gray-700">{rec}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
