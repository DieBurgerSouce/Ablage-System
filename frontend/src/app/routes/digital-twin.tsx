import { createFileRoute } from '@tanstack/react-router';
import { DigitalTwinDashboard } from '@/features/digital-twin/components/DigitalTwinDashboard';

export const Route = createFileRoute('/digital-twin')({
  component: DigitalTwinPage,
});

function DigitalTwinPage() {
  return (
    <div className="p-8 space-y-8">
      <DigitalTwinDashboard />
    </div>
  );
}
