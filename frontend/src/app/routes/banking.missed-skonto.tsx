/**
 * Banking Missed Skonto Route
 * Route fuer verpasste Skonto-Uebersicht
 */

import { createFileRoute } from '@tanstack/react-router';
import { MissedSkontoDashboard } from '@/features/banking/missed-skonto';

export const Route = createFileRoute('/banking/missed-skonto')({
  component: MissedSkontoPage,
});

function MissedSkontoPage() {
  return <MissedSkontoDashboard />;
}
