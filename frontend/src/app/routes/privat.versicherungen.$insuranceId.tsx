/**
 * Privat Versicherungen Detail Route
 *
 * Detailansicht einer einzelnen Versicherung.
 */

import { createFileRoute } from '@tanstack/react-router';
import { InsuranceDetailPage } from '@/features/privat';

export const Route = createFileRoute('/privat/versicherungen/$insuranceId')({
  component: InsuranceDetailPage,
});
