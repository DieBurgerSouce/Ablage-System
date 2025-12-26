import { createFileRoute } from '@tanstack/react-router'
import { SupplierFoldersView } from '@/features/ablage'

// Index-Route: Zeigt Ordner-Auswahl (Spargelmesser1/Folie)
export const Route = createFileRoute('/lieferanten/$supplierId/')({
  component: SupplierFoldersView,
})
