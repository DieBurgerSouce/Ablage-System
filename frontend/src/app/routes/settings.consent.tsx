/**
 * Settings Consent Route
 *
 * DSGVO Art. 6, 7 - Self-Service Einwilligungsverwaltung
 */

import { createFileRoute } from '@tanstack/react-router';
import { ConsentPortal } from '@/features/settings/consent';

export const Route = createFileRoute('/settings/consent')({
  component: ConsentPortal,
});
