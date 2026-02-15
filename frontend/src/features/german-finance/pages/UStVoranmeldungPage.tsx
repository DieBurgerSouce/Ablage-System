/**
 * UStVoranmeldungPage
 *
 * USt-Voranmeldung overview page
 */

import { useState } from 'react';
import { UStReportList, UStReportView } from '../components';
import { useUStReport } from '../hooks/use-german-finance-queries';
import { UI_LABELS } from '../types/german-finance-types';
import { Button } from '@/components/ui/button';
import { ArrowLeft } from 'lucide-react';

export function UStVoranmeldungPage() {
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const { data: selectedReport } = useUStReport(selectedReportId || '', {
    enabled: !!selectedReportId,
  });

  if (selectedReportId && selectedReport) {
    return (
      <div className="container mx-auto space-y-6 py-8">
        <Button
          variant="ghost"
          onClick={() => setSelectedReportId(null)}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          Zurück zur Übersicht
        </Button>
        <UStReportView
          report={selectedReport}
          onPrint={() => window.print()}
        />
      </div>
    );
  }

  return (
    <div className="container mx-auto space-y-6 py-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">{UI_LABELS.ust.title}</h1>
        <p className="text-muted-foreground">{UI_LABELS.ust.subtitle}</p>
      </div>
      <UStReportList onViewReport={setSelectedReportId} />
    </div>
  );
}
