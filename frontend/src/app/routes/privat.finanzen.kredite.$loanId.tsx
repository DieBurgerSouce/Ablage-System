/**
 * Privat Finanzen Kredit Detail Route
 *
 * Detailansicht eines einzelnen Kredits.
 */

import { createFileRoute } from '@tanstack/react-router';
import { LoanDetailPage } from '@/features/privat';

export const Route = createFileRoute('/privat/finanzen/kredite/$loanId')({
  component: LoanDetailPage,
});
