/**
 * Data Quality Route
 *
 * Route for the Data Quality Cockpit at /admin/data-quality
 */

import { createFileRoute } from '@tanstack/react-router';
import { DataQualityCockpit } from '@/features/ceo-dashboard/components/DataQualityCockpit';

export const Route = createFileRoute('/admin/data-quality')({
  component: DataQualityCockpit,
});
