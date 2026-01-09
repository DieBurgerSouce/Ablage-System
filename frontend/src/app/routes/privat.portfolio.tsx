/**
 * Privat Portfolio Route
 *
 * Portfolio-Dashboard mit Vermoegensübersicht,
 * finanzieller Gesundheit und Zielen.
 */

import { createFileRoute } from '@tanstack/react-router';
import { PortfolioPage } from '@/features/privat';

export const Route = createFileRoute('/privat/portfolio')({
  component: PortfolioPage,
});
