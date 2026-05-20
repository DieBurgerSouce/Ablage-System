/**
 * Banking Missed Skonto Route
 * Route für verpasste Skonto-Übersicht
 */

import { createFileRoute } from '@tanstack/react-router';
import { MissedSkontoDashboard } from '@/features/banking/missed-skonto';

export const Route = createFileRoute('/banking/missed-skonto')({
  component: MissedSkontoPage,
});

function MissedSkontoPage() {
  return <MissedSkontoDashboard />;
}
