/**
 * Privat Lebenslagen Route
 *
 * Lebenslagen-Assistent für wichtige Lebensereignisse.
 */

import { createFileRoute } from '@tanstack/react-router';
import { LifeEventsPage } from '@/features/life-events';

export const Route = createFileRoute('/privat/life-events')({
  component: LifeEventsPage,
});
