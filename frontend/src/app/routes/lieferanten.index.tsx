import { createFileRoute } from '@tanstack/react-router'
import { LieferantenPage } from '@/features/ablage'

export const Route = createFileRoute('/lieferanten/')({
  component: LieferantenPage,
})
