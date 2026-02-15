/**
 * Route: /german-finance/bwa
 *
 * BWA page route
 */

import { createFileRoute } from '@tanstack/react-router';
import { BWAPage } from '@/features/german-finance';

export const Route = createFileRoute('/german-finance/bwa')({
  component: BWAPage,
});
