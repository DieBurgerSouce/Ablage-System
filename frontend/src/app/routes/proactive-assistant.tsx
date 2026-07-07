// Proactive Assistant Route

import { createFileRoute } from '@tanstack/react-router';
import { frozenModuleGuard } from '@/lib/frozen-modules';
import { ProactiveAssistantPage } from '@/features/proactive-assistant';

export const Route = createFileRoute('/proactive-assistant')({
  // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts)
  beforeLoad: () => frozenModuleGuard('ai_speculative'),
  component: ProactiveAssistantPage,
});
