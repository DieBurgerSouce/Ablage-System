import { createFileRoute } from '@tanstack/react-router'
import { CategoryDocumentList } from '@/features/ablage'

export const Route = createFileRoute('/kunden/$customerId/$folderId/$category')({
  component: () => <CategoryDocumentList entityType="customer" />,
})
