/**
 * Developer Portal Route
 * Route für das Developer Portal mit API-Dokumentation, SDKs und Webhooks
 */

import { createFileRoute } from '@tanstack/react-router';
import { DeveloperPortalPage } from '@/features/developer-portal';

export const Route = createFileRoute('/developer')({
  component: DeveloperPortalPage,
});
