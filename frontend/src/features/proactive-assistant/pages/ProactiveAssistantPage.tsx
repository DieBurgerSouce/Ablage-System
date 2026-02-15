// Proactive Assistant Main Page

import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Sparkles, BarChart3 } from 'lucide-react';
import { HintDashboardWidget } from '../components/HintDashboardWidget';
import { HintList } from '../components/HintList';
import { HintStatistics } from '../components/HintStatistics';
import { useGenerateHintsMutation } from '../hooks/use-proactive-assistant-queries';
import { UI_LABELS } from '../types/proactive-assistant-types';
import { useState } from 'react';

export function ProactiveAssistantPage() {
  const [showStatistics, setShowStatistics] = useState(false);
  const generateMutation = useGenerateHintsMutation();

  const handleGenerateHints = () => {
    generateMutation.mutate();
  };

  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Page Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <Sparkles className="h-8 w-8 text-yellow-500" />
            {UI_LABELS.pageTitle}
          </h1>
          <p className="text-muted-foreground mt-1">
            {UI_LABELS.pageSubtitle}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowStatistics(!showStatistics)}
          >
            <BarChart3 className="h-4 w-4 mr-2" />
            {showStatistics ? 'Hinweise anzeigen' : 'Statistiken anzeigen'}
          </Button>
          <Button
            onClick={handleGenerateHints}
            disabled={generateMutation.isPending}
          >
            <Sparkles className="h-4 w-4 mr-2" />
            {UI_LABELS.actions.generateHints}
          </Button>
        </div>
      </div>

      <Separator />

      {/* Dashboard Widget */}
      <HintDashboardWidget />

      {/* Content Toggle */}
      {showStatistics ? (
        <HintStatistics />
      ) : (
        <>
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold">Aktuelle Hinweise</h2>
          </div>
          <HintList />
        </>
      )}
    </div>
  );
}
