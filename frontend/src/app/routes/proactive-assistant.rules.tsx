// Proactive Assistant Rules Route

import { createFileRoute } from '@tanstack/react-router';
import { HintRulesPage } from '@/features/proactive-assistant';

export const Route = createFileRoute('/proactive-assistant/rules')({
  component: HintRulesPage,
});
