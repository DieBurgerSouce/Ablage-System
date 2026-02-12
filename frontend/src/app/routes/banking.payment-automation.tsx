/**
 * Banking Payment Automation Route
 * Route für Auto-Zahlungsvorschläge Dashboard
 */

import { createFileRoute } from '@tanstack/react-router';
import { PaymentAutomationPage } from '@/features/banking/payment-automation';

export const Route = createFileRoute('/banking/payment-automation')({
  component: PaymentAutomationPage,
});
