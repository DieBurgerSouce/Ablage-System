/**
 * Streckengeschäft Klassifikationen Route
 *
 * Displays the classification list view for drop shipments.
 * Uses the main dashboard with classifications tab active.
 */

import { createFileRoute } from '@tanstack/react-router';
import { StreckengeschaeftDashboard } from '@/components/streckengeschaeft';

export const Route = createFileRoute('/streckengeschaeft/klassifikationen')({
  component: StreckengeschaeftDashboard,
});
