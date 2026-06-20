import { createFileRoute } from '@tanstack/react-router'
import { lazyRoute } from '@/lib/lazyRoute'

const CrossCompanyPage = lazyRoute(() => import('@/features/relationships/components/CrossCompanyPage').then(m => ({ default: m.CrossCompanyPage })))

export const Route = createFileRoute('/relationships')({
  component: RouteComponent,
})

function RouteComponent() {
  return <CrossCompanyPage />
}
