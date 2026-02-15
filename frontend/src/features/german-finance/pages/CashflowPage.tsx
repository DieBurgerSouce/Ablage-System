/**
 * CashflowPage
 *
 * Cashflow dashboard with forecast, warnings, and scenarios
 */

import { LiquidityWarningBanner, CashflowForecastChart, ScenarioSimulator } from '../components';
import { UI_LABELS } from '../types/german-finance-types';

export function CashflowPage() {
  return (
    <div className="container mx-auto space-y-6 py-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">{UI_LABELS.cashflow.title}</h1>
        <p className="text-muted-foreground">{UI_LABELS.cashflow.subtitle}</p>
      </div>

      {/* Liquidity Warnings */}
      <LiquidityWarningBanner />

      {/* Cashflow Forecast */}
      <CashflowForecastChart defaultDays={30} />

      {/* Scenario Simulator */}
      <ScenarioSimulator />
    </div>
  );
}
