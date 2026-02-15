// Proactive Assistant Route

import { createFileRoute } from '@tanstack/react-router';
import { ProactiveAssistantPage } from '@/features/proactive-assistant';

export const Route = createFileRoute('/proactive-assistant')({
  component: ProactiveAssistantPage,
});
