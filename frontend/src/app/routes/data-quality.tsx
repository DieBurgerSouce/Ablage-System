import { createFileRoute } from '@tanstack/react-router';
import { DataQualityDashboard } from '@/features/data-quality/components/DataQualityDashboard';

export const Route = createFileRoute('/data-quality')({
  component: DataQualityPage,
});

function DataQualityPage() {
  return (
    <div className="p-8 space-y-8">
      <DataQualityDashboard />
    </div>
  );
}
