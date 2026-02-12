import { createFileRoute } from '@tanstack/react-router'
import { CashflowForecastReport } from '@/features/reports/components/CashflowForecastReport'

export const Route = createFileRoute('/reports/cashflow-forecast')({
  component: CashflowForecastReport,
})
