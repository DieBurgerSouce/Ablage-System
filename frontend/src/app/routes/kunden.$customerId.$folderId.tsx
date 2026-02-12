import { createFileRoute, Outlet } from '@tanstack/react-router'

// Layout-Route für Ordner - rendert Child-Routes via Outlet
export const Route = createFileRoute('/kunden/$customerId/$folderId')({
  component: () => <Outlet />,
})
