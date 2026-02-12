/**
 * Validation Admin Route
 *
 * Route für das Validierungs-Dashboard im Admin-Bereich.
 */

import { createFileRoute } from '@tanstack/react-router';
import { ValidationDashboard } from '@/features/validation';

export const Route = createFileRoute('/admin/validation')({
  component: ValidationDashboard,
});
