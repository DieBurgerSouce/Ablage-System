/**
 * MLOps Admin Route
 *
 * Route fuer das Machine Learning Operations Dashboard.
 */

import { createFileRoute } from '@tanstack/react-router';
import { MLOpsPage } from '@/features/admin/mlops';

export const Route = createFileRoute('/admin/mlops')({
  component: MLOpsPage,
});
