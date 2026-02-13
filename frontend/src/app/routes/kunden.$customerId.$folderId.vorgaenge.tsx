import { createFileRoute } from '@tanstack/react-router'
import { TransactionsView } from '@/features/ablage'

export const Route = createFileRoute('/kunden/$customerId/$folderId/vorgaenge')({
  component: () => <TransactionsView entityType="customer" />,
})
