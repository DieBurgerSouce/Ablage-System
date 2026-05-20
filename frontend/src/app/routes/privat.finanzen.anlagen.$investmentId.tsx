/**
 * Privat Finanzen Geldanlage Detail Route
 *
 * Detailansicht einer einzelnen Geldanlage.
 */

import { createFileRoute } from '@tanstack/react-router';
import { InvestmentDetailPage } from '@/features/privat';

export const Route = createFileRoute('/privat/finanzen/anlagen/$investmentId')({
  component: InvestmentDetailPage,
});
