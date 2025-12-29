import { createFileRoute } from '@tanstack/react-router'
import { FinanceCategoryDocumentList } from '@/features/finanzen'

export const Route = createFileRoute('/finanzen/$year/$category')({
  component: FinanceCategoryDocumentList,
})
