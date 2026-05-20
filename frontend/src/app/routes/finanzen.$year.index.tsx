import { createFileRoute } from '@tanstack/react-router'
import { FinanzenYearCategoriesView } from '@/features/finanzen'

export const Route = createFileRoute('/finanzen/$year/')({
  component: FinanzenYearCategoriesView,
})
