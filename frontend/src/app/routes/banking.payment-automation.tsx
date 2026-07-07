/**
 * Banking Payment Automation Route
 * Route für Auto-Zahlungsvorschläge Dashboard
 */

import { createFileRoute } from '@tanstack/react-router';
import { frozenModuleGuard } from '@/lib/frozen-modules';
import { PaymentAutomationPage } from '@/features/banking/payment-automation';

export const Route = createFileRoute('/banking/payment-automation')({
  // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts)
  beforeLoad: () => frozenModuleGuard('banking'),
  component: PaymentAutomationPage,
});
