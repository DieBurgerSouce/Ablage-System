/**
 * Privat Lebenslagen Route
 *
 * Lebenslagen-Assistent fuer wichtige Lebensereignisse.
 */

import { createFileRoute } from '@tanstack/react-router';
import { LifeEventsPage } from '@/features/life-events';

export const Route = createFileRoute('/privat/life-events')({
  component: LifeEventsPage,
});
