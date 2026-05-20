import { createFileRoute } from '@tanstack/react-router'
import { IntegrationSyncPage } from '@/features/integrations/components/IntegrationSyncPage'

export const Route = createFileRoute('/admin/integration-sync')({
  component: IntegrationSyncPage,
})
