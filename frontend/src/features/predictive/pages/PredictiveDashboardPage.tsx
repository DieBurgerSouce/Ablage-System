/**
 * PredictiveDashboardPage - Seite fuer Vorhersage-Dashboard
 *
 * Zentrale Uebersichtsseite mit KI-basierten Vorhersagen:
 * - Cashflow-Prognose (30/60/90 Tage)
 * - Zahlungsvorhersagen mit Risikobewertung
 * - System-Gesundheitsmetriken
 */

import { CashflowForecast } from '../components/CashflowForecast';
import { PaymentPredictions } from '../components/PaymentPredictions';
import { SystemHealthDashboard } from '../components/SystemHealthDashboard';

export function PredictiveDashboardPage() {
  return (
    <div className="space-y-6 p-6 max-w-7xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold">Vorhersagen & Prognosen</h1>
        <p className="text-muted-foreground text-sm mt-1">
          KI-basierte Vorhersagen fuer Cashflow, Zahlungen und
          Systemgesundheit
        </p>
      </div>

      <div className="space-y-6">
        <CashflowForecast />
        <PaymentPredictions />
        <SystemHealthDashboard />
      </div>
    </div>
  );
}
