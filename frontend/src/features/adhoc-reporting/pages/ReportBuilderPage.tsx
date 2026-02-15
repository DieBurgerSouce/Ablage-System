/**
 * ReportBuilderPage
 * German Enterprise Document Platform
 */

import { useNavigate } from '@tanstack/react-router';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ReportBuilder } from '../components/ReportBuilder';
import { useCreateReport } from '../hooks/use-adhoc-reporting-queries';
import type { ReportConfig } from '../types/adhoc-reporting-types';
import { toBackendReportDefinition } from '../types/adhoc-reporting-types';

export function ReportBuilderPage() {
  const navigate = useNavigate();
  const createReportMutation = useCreateReport();

  const handleSave = async (config: ReportConfig) => {
    try {
      const report = await createReportMutation.mutateAsync(toBackendReportDefinition(config));
      // Navigate to the created report
      navigate({ to: `/adhoc-reporting/${report.id}` });
    } catch (error) {
      console.error('Failed to create report:', error);
    }
  };

  const handleCancel = () => {
    navigate({ to: '/adhoc-reporting' });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center space-x-4">
        <Button variant="ghost" size="icon" onClick={() => navigate({ to: '/adhoc-reporting' })}>
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Neuen Report erstellen</h1>
          <p className="text-muted-foreground mt-2">
            Konfigurieren Sie Ihren benutzerdefinierten Report
          </p>
        </div>
      </div>

      {/* Builder */}
      <ReportBuilder
        onSave={handleSave}
        onCancel={handleCancel}
        isSaving={createReportMutation.isPending}
      />
    </div>
  );
}
