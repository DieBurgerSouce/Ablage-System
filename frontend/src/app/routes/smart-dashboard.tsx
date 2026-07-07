// Smart Dashboard Route
// Route: /smart-dashboard

import { createFileRoute } from '@tanstack/react-router';
import { frozenModuleGuard } from '@/lib/frozen-modules';
import { SmartDashboardPage } from '@/features/smart-dashboard';

export const Route = createFileRoute('/smart-dashboard')({
  // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts)
  beforeLoad: () => frozenModuleGuard('ai_speculative'),
  component: SmartDashboardPage,
});
