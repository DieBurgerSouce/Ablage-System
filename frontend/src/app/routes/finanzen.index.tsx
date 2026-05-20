import { createFileRoute } from '@tanstack/react-router'
import { FinanzenPage } from '@/features/finanzen'

export const Route = createFileRoute('/finanzen/')({
  component: FinanzenPage,
})
