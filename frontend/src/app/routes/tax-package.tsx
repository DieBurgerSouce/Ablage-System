/**
 * Tax Package Route - Steuerberater-Paket
 *
 * Route für automatische Buchhaltungspakete
 */

import { createFileRoute } from '@tanstack/react-router';
import { TaxPackagePage } from '@/features/tax-package';

export const Route = createFileRoute('/tax-package')({
  component: TaxPackagePage,
});
