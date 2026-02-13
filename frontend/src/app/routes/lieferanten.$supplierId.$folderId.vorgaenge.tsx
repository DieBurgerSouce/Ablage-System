import { createFileRoute } from '@tanstack/react-router'
import { TransactionsView } from '@/features/ablage'

export const Route = createFileRoute('/lieferanten/$supplierId/$folderId/vorgaenge')({
  component: () => <TransactionsView entityType="supplier" />,
})
