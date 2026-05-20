import { createFileRoute } from '@tanstack/react-router'
import { CategoryDocumentList } from '@/features/ablage'

export const Route = createFileRoute('/lieferanten/$supplierId/$folderId/$category')({
  component: () => <CategoryDocumentList entityType="supplier" />,
})
