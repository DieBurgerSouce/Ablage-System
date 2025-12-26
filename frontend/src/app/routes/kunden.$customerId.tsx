import { createFileRoute, Outlet } from '@tanstack/react-router'

// Layout-Route fuer Kunden-Details - rendert Child-Routes via Outlet
export const Route = createFileRoute('/kunden/$customerId')({
  component: () => <Outlet />,
})
