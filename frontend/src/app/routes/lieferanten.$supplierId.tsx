import { createFileRoute, Outlet } from '@tanstack/react-router'

// Layout-Route für Lieferanten-Details - rendert Child-Routes via Outlet
export const Route = createFileRoute('/lieferanten/$supplierId')({
  component: () => <Outlet />,
})
