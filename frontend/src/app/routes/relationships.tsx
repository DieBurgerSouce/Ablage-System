import { createFileRoute } from '@tanstack/react-router'
import { CrossCompanyPage } from '@/features/relationships/components/CrossCompanyPage'

export const Route = createFileRoute('/relationships')({
  component: RouteComponent,
})

function RouteComponent() {
  return <CrossCompanyPage />
}
