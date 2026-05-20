/**
 * German Finance Types
 *
 * Type definitions for USt-Voranmeldung (VAT), BWA, and Cashflow features
 */

// ============================================================================
// Backend Types (API responses)
// ============================================================================

export interface UStReportBackend {
  id: string;
  year: number;
  month: number;
  vorsteuer: number; // Input VAT (what you paid)
  umsatzsteuer: number; // Output VAT (what you collected)
  zahllast: number; // Net VAT payable (Umsatzsteuer - Vorsteuer)
  umsatzsteuer_19: number;
  umsatzsteuer_7: number;
  umsatzsteuer_0: number;
  status: 'draft' | 'submitted' | 'approved';
  created_at: string;
  submitted_at: string | null;
  notes: string | null;
}

export interface BWASectionBackend {
  name: string;
  amount: number;
  percentage: number | null;
}

export interface BWAReportBackend {
  id: string;
  year: number;
  month: number;
  schema: 'skr03' | 'skr04';
  revenue: number;
  expenses: number;
  profit: number;
  sections: BWASectionBackend[];
  status: 'draft' | 'final';
  created_at: string;
}

export interface CashflowForecastBackend {
  date: string;
  expected_income: number;
  expected_expenses: number;
  net_cashflow: number;
  cumulative: number;
  confidence: number; // 0-100
}

export interface LiquidityWarningBackend {
  severity: 'critical' | 'warning' | 'info';
  message: string;
  expected_date: string | null;
  shortfall_amount: number | null;
}

export interface CashflowAdjustmentBackend {
  category: string;
  amount: number;
  date: string;
  description: string | null;
}

export interface CashflowScenarioBackend {
  id: string;
  name: string;
  adjustments: CashflowAdjustmentBackend[];
  result_forecast: CashflowForecastBackend[];
  created_at: string;
}

export interface CashflowHistoryBackend {
  date: string;
  actual_income: number;
  actual_expenses: number;
  net_cashflow: number;
  cumulative: number;
}

// ============================================================================
// Frontend Types (UI state)
// ============================================================================

export interface UStReport {
  id: string;
  year: number;
  month: number;
  vorsteuer: number;
  umsatzsteuer: number;
  zahllast: number;
  umsatzsteuer19: number;
  umsatzsteuer7: number;
  umsatzsteuer0: number;
  status: 'draft' | 'submitted' | 'approved';
  createdAt: Date;
  submittedAt: Date | null;
  notes: string | null;
}

export interface BWASection {
  name: string;
  amount: number;
  percentage: number | null;
}

export interface BWAReport {
  id: string;
  year: number;
  month: number;
  schema: 'skr03' | 'skr04';
  revenue: number;
  expenses: number;
  profit: number;
  sections: BWASection[];
  status: 'draft' | 'final';
  createdAt: Date;
}

export interface CashflowForecast {
  date: Date;
  expectedIncome: number;
  expectedExpenses: number;
  netCashflow: number;
  cumulative: number;
  confidence: number;
}

export interface LiquidityWarning {
  severity: 'critical' | 'warning' | 'info';
  message: string;
  expectedDate: Date | null;
  shortfallAmount: number | null;
}

export interface CashflowAdjustment {
  category: string;
  amount: number;
  date: Date;
  description: string | null;
}

export interface CashflowScenario {
  id: string;
  name: string;
  adjustments: CashflowAdjustment[];
  resultForecast: CashflowForecast[];
  createdAt: Date;
}

export interface CashflowHistory {
  date: Date;
  actualIncome: number;
  actualExpenses: number;
  netCashflow: number;
  cumulative: number;
}

// ============================================================================
// Transform Functions (Backend -> Frontend)
// ============================================================================

export function transformUStReport(backend: UStReportBackend): UStReport {
  return {
    id: backend.id,
    year: backend.year,
    month: backend.month,
    vorsteuer: backend.vorsteuer,
    umsatzsteuer: backend.umsatzsteuer,
    zahllast: backend.zahllast,
    umsatzsteuer19: backend.umsatzsteuer_19,
    umsatzsteuer7: backend.umsatzsteuer_7,
    umsatzsteuer0: backend.umsatzsteuer_0,
    status: backend.status,
    createdAt: new Date(backend.created_at),
    submittedAt: backend.submitted_at ? new Date(backend.submitted_at) : null,
    notes: backend.notes,
  };
}

export function transformBWAReport(backend: BWAReportBackend): BWAReport {
  return {
    id: backend.id,
    year: backend.year,
    month: backend.month,
    schema: backend.schema,
    revenue: backend.revenue,
    expenses: backend.expenses,
    profit: backend.profit,
    sections: backend.sections.map(s => ({
      name: s.name,
      amount: s.amount,
      percentage: s.percentage,
    })),
    status: backend.status,
    createdAt: new Date(backend.created_at),
  };
}

export function transformCashflowForecast(backend: CashflowForecastBackend): CashflowForecast {
  return {
    date: new Date(backend.date),
    expectedIncome: backend.expected_income,
    expectedExpenses: backend.expected_expenses,
    netCashflow: backend.net_cashflow,
    cumulative: backend.cumulative,
    confidence: backend.confidence,
  };
}

export function transformLiquidityWarning(backend: LiquidityWarningBackend): LiquidityWarning {
  return {
    severity: backend.severity,
    message: backend.message,
    expectedDate: backend.expected_date ? new Date(backend.expected_date) : null,
    shortfallAmount: backend.shortfall_amount,
  };
}

export function transformCashflowScenario(backend: CashflowScenarioBackend): CashflowScenario {
  return {
    id: backend.id,
    name: backend.name,
    adjustments: backend.adjustments.map(a => ({
      category: a.category,
      amount: a.amount,
      date: new Date(a.date),
      description: a.description,
    })),
    resultForecast: backend.result_forecast.map(transformCashflowForecast),
    createdAt: new Date(backend.created_at),
  };
}

export function transformCashflowHistory(backend: CashflowHistoryBackend): CashflowHistory {
  return {
    date: new Date(backend.date),
    actualIncome: backend.actual_income,
    actualExpenses: backend.actual_expenses,
    netCashflow: backend.net_cashflow,
    cumulative: backend.cumulative,
  };
}

// ============================================================================
// UI Labels (German)
// ============================================================================

export const UI_LABELS = {
  ust: {
    title: 'USt-Voranmeldung',
    subtitle: 'Umsatzsteuer-Voranmeldungen erstellen und verwalten',
    generate: 'USt-Voranmeldung erstellen',
    vorsteuer: 'Vorsteuer (gezahlt)',
    umsatzsteuer: 'Umsatzsteuer (erhalten)',
    umsatzsteuer19: 'Umsatzsteuer 19%',
    umsatzsteuer7: 'Umsatzsteuer 7%',
    umsatzsteuer0: 'Umsatzsteuer 0%',
    zahllast: 'Zahllast',
    status: {
      draft: 'Entwurf',
      submitted: 'Eingereicht',
      approved: 'Genehmigt',
    },
  },
  bwa: {
    title: 'BWA',
    subtitle: 'Betriebswirtschaftliche Auswertungen',
    generate: 'BWA erstellen',
    schema: 'Kontenrahmen',
    revenue: 'Erlöse',
    expenses: 'Aufwendungen',
    profit: 'Betriebsergebnis',
    status: {
      draft: 'Entwurf',
      final: 'Final',
    },
  },
  cashflow: {
    title: 'Cashflow-Prognose',
    subtitle: 'Liquiditätsplanung und Szenarien',
    forecast: 'Prognose',
    expectedIncome: 'Erwartete Einnahmen',
    expectedExpenses: 'Erwartete Ausgaben',
    netCashflow: 'Netto-Cashflow',
    cumulative: 'Kumuliert',
    confidence: 'Konfidenz',
    warnings: 'Liquiditätswarnungen',
    scenarios: 'Szenarien',
    runScenario: 'Simulation starten',
    createScenario: 'Neues Szenario',
    addAdjustment: 'Anpassung hinzufügen',
  },
  common: {
    year: 'Jahr',
    month: 'Monat',
    date: 'Datum',
    amount: 'Betrag',
    category: 'Kategorie',
    description: 'Beschreibung',
    actions: 'Aktionen',
    loading: 'Lädt...',
    error: 'Fehler beim Laden',
    noData: 'Keine Daten verfügbar',
    save: 'Speichern',
    cancel: 'Abbrechen',
    delete: 'Löschen',
    print: 'Drucken',
  },
};

// ============================================================================
// Request Types
// ============================================================================

export interface GenerateUStRequest {
  year: number;
  month: number;
  include_corrections?: boolean;
}

export interface GenerateBWARequest {
  year: number;
  month: number;
  schema: 'skr03' | 'skr04';
}

export interface UpdateCashflowRequest {
  date: string;
  actual_income?: number;
  actual_expenses?: number;
}

export interface RunScenarioRequest {
  name: string;
  adjustments: Array<{
    category: string;
    amount: number;
    date: string;
    description?: string;
  }>;
}
