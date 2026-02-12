import { createFileRoute } from '@tanstack/react-router'
import { TransactionsView } from '@/features/ablage'

export const Route = createFileRoute('/lieferanten/$supplierId/$folderId/vorgänge')({
  component: () => <TransactionsView entityType="supplier" />,
})
