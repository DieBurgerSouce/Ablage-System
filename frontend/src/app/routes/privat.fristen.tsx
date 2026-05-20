/**
 * Privat Fristen Route
 *
 * Fristen-Übersicht und Kalender-Export.
 */

import { createFileRoute } from '@tanstack/react-router';
import { DeadlinesPage } from '@/features/privat';

export const Route = createFileRoute('/privat/fristen')({
  component: DeadlinesPage,
});
