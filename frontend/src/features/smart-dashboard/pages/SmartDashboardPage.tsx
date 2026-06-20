// Smart Dashboard Page Component
// Main page with tab navigation, KPI grid, and tab-specific content

import { useState } from 'react';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { RefreshCw, AlertCircle } from 'lucide-react';
import {
  DashboardTabBar,
  KPIGrid,
  WidgetContainer,
} from '../components';
import {
  useKPIs,
  useTabData,
  useInvalidateSmartDashboard,
} from '../hooks/use-smart-dashboard-queries';
import { type DashboardTabKey, UI_LABELS } from '../types/smart-dashboard-types';

export function SmartDashboardPage() {
  const [activeTab, setActiveTab] = useState<DashboardTabKey>('uebersicht');
  const invalidateDashboard = useInvalidateSmartDashboard();

  // Fetch KPIs (real-time)
  const {
    data: kpis,
    isLoading: kpisLoading,
    isError: kpisError,
  } = useKPIs();

  // Fetch tab-specific data
  const {
    data: tabData,
    isLoading: tabLoading,
    isError: tabError,
  } = useTabData(activeTab);

  const isLoading = kpisLoading || tabLoading;
  const isError = kpisError || tabError;

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{UI_LABELS.PAGE_TITLE}</h1>
          <p className="text-muted-foreground">{UI_LABELS.PAGE_SUBTITLE}</p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={invalidateDashboard}
          disabled={isLoading}
        >
          <RefreshCw className={`mr-2 h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          {UI_LABELS.ACTION_REFRESH}
        </Button>
      </div>

      {/* Tab Navigation */}
      <DashboardTabBar activeTab={activeTab} onTabChange={setActiveTab} />

      {/* Error State */}
      {isError && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>{UI_LABELS.ERROR}</AlertTitle>
          <AlertDescription>
            {UI_LABELS.ERROR}. Bitte versuchen Sie es erneut.
          </AlertDescription>
        </Alert>
      )}

      {/* KPI Grid */}
      {kpisLoading ? (
        <div className="grid gap-4 grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      ) : kpis && kpis.length > 0 ? (
        <KPIGrid kpis={kpis} />
      ) : null}

      {/* Tab-Specific Content */}
      <div className="mt-8">
        {tabLoading ? (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {[...Array(3)].map((_, i) => (
              <Skeleton key={i} className="h-64" />
            ))}
          </div>
        ) : tabData && tabData.widgets && tabData.widgets.length > 0 ? (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {tabData.widgets.map((widget) => (
              <WidgetContainer
                key={widget.widgetId}
                title={widget.title}
                widgetId={widget.widgetId}
              >
                {/* Widget content placeholder - would render based on widgetType */}
                <div className="text-sm text-muted-foreground">
                  Widget-Typ: {widget.widgetType}
                </div>
                <pre className="text-xs mt-2 p-2 bg-muted rounded">
                  {JSON.stringify(widget.data, null, 2)}
                </pre>
              </WidgetContainer>
            ))}
          </div>
        ) : (
          <div className="text-center py-12 text-muted-foreground">
            {UI_LABELS.NO_DATA}
          </div>
        )}
      </div>
    </div>
  );
}
