/**
 * KI-Pipeline Route
 * Main KI-Pipeline page at /ki-pipeline
 */

import { createFileRoute } from '@tanstack/react-router';
import { KIPipelinePage } from '@/features/ki-pipeline';

export const Route = createFileRoute('/ki-pipeline')({
  component: KIPipelinePage,
});
