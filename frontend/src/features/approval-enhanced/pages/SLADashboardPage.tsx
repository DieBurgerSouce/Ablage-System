/**
 * SLADashboardPage
 * SLA metrics dashboard with breach alerts
 */

import { Separator } from '@/components/ui/separator';
import { SLADashboard } from '../components/SLADashboard';
import { SLABreachAlert } from '../components/SLABreachAlert';
import { useSLAMetrics } from '../hooks/use-approval-enhanced-queries';
import { UI_LABELS } from '../types/approval-enhanced-types';

export function SLADashboardPage() {
  const { data: metrics } = useSLAMetrics();

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">{UI_LABELS.sla.title}</h1>
        <p className="text-muted-foreground">{UI_LABELS.sla.subtitle}</p>
      </div>

      <Separator />

      {/* SLA Breach Alert */}
      {metrics && metrics.slaBreachCount > 0 && (
        <SLABreachAlert
          breachCount={metrics.slaBreachCount}
          severity={metrics.slaBreachCount > 5 ? 'error' : 'warning'}
        />
      )}

      {/* Dashboard */}
      <SLADashboard />
    </div>
  );
}
