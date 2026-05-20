/**
 * Streckengeschäft Dashboard Index Route
 *
 * Main dashboard for drop shipment classification overview.
 */

import { createFileRoute } from '@tanstack/react-router';
import { StreckengeschaeftDashboard } from '@/components/streckengeschaeft';

export const Route = createFileRoute('/streckengeschaeft/')({
  component: StreckengeschaeftDashboard,
});
