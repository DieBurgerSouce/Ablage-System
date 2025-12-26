import { createFileRoute, Outlet } from '@tanstack/react-router'

// Layout-Route fuer Lieferanten-Details - rendert Child-Routes via Outlet
export const Route = createFileRoute('/lieferanten/$supplierId')({
  component: () => <Outlet />,
})
