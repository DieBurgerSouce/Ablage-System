/**
 * Streckengeschäft Classification Detail Route
 *
 * Detailed view for a single drop shipment classification.
 */

import { createFileRoute } from '@tanstack/react-router';
import { ClassificationDetail } from '@/components/streckengeschaeft';

export const Route = createFileRoute('/streckengeschaeft/$classificationId')({
  component: ClassificationDetail,
});
