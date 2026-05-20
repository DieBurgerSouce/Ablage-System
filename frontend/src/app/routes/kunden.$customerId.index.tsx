import { createFileRoute } from '@tanstack/react-router'
import { CustomerFoldersView } from '@/features/ablage'

// Index-Route: Zeigt Ordner-Auswahl (Spargelmesser/Folie)
export const Route = createFileRoute('/kunden/$customerId/')({
  component: CustomerFoldersView,
})
