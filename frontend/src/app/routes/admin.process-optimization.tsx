/**
 * Process Optimization Admin Route
 *
 * Route für das Process Mining und Optimierungs-Dashboard.
 * Vision 2.0 Phase 3
 */

import { createFileRoute } from '@tanstack/react-router';
import { ProcessOptimizationPage } from '@/features/admin/process-optimization';

export const Route = createFileRoute('/admin/process-optimization')({
  component: ProcessOptimizationPage,
});
