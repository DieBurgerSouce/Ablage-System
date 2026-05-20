/**
 * Route: /german-finance/ust
 *
 * USt-Voranmeldung page route
 */

import { createFileRoute } from '@tanstack/react-router';
import { UStVoranmeldungPage } from '@/features/german-finance';

export const Route = createFileRoute('/german-finance/ust')({
  component: UStVoranmeldungPage,
});
