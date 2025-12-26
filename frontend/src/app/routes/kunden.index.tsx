import { createFileRoute } from '@tanstack/react-router'
import { KundenPage } from '@/features/ablage'

export const Route = createFileRoute('/kunden/')({
  component: KundenPage,
})
