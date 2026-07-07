import { createFileRoute } from '@tanstack/react-router';
import { frozenModuleGuard } from '@/lib/frozen-modules';
import { DigitalTwinDashboard } from '@/features/digital-twin/components/DigitalTwinDashboard';

export const Route = createFileRoute('/digital-twin')({
  // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts)
  beforeLoad: () => frozenModuleGuard('ai_speculative'),
  component: DigitalTwinPage,
});

function DigitalTwinPage() {
  return (
    <div className="p-8 space-y-8">
      <DigitalTwinDashboard />
    </div>
  );
}
