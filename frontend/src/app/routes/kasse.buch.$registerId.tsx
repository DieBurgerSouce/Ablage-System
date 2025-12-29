/**
 * Kassenbuch Detail Route
 *
 * Detailansicht eines Kassenbuchs mit allen Eintraegen.
 */

import { createFileRoute } from '@tanstack/react-router';
import { CashBookPage } from '@/features/cash';

export const Route = createFileRoute('/kasse/buch/$registerId')({
  component: CashBookPage,
});
