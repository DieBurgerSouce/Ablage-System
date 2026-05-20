import { createFileRoute } from '@tanstack/react-router'
import { FolderCategoriesView } from '@/features/ablage'

export const Route = createFileRoute('/kunden/$customerId/$folderId/')({
  component: () => <FolderCategoriesView entityType="customer" />,
})
