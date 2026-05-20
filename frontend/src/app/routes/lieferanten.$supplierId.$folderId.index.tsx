import { createFileRoute } from '@tanstack/react-router'
import { FolderCategoriesView } from '@/features/ablage'

export const Route = createFileRoute('/lieferanten/$supplierId/$folderId/')({
  component: () => <FolderCategoriesView entityType="supplier" />,
})
