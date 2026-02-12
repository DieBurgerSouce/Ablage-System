import { createFileRoute } from '@tanstack/react-router'
import { TransactionsView } from '@/features/ablage'

export const Route = createFileRoute('/kunden/$customerId/$folderId/vorgänge')({
  component: () => <TransactionsView entityType="customer" />,
})
