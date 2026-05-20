import { createFileRoute } from "@tanstack/react-router";
import { AlertCenter } from "@/features/alerts/AlertCenter";

export const Route = createFileRoute("/alerts")({
  component: AlertsPage,
});

function AlertsPage() {
  return <AlertCenter />;
}
