import { createFileRoute } from '@tanstack/react-router'
import { CostAnalysisReport } from '@/features/reports/components/CostAnalysisReport'

export const Route = createFileRoute('/reports/cost-analysis')({
  component: CostAnalysisReport,
})
