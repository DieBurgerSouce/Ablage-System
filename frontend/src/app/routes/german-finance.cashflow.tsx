/**
 * Route: /german-finance/cashflow
 *
 * Cashflow page route
 */

import { createFileRoute } from '@tanstack/react-router';
import { CashflowPage } from '@/features/german-finance';

export const Route = createFileRoute('/german-finance/cashflow')({
  component: CashflowPage,
});
