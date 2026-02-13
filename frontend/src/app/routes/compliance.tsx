/**
 * Compliance Cockpit Route
 */

import { createFileRoute } from '@tanstack/react-router';
import { ComplianceCockpitPage } from '@/features/compliance';

export const Route = createFileRoute('/compliance')({
  component: ComplianceCockpitPage,
});
