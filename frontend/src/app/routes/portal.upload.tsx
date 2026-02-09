/**
 * Portal Upload Route
 *
 * Kundenportal Dokumenten-Upload Seite.
 */

import { createFileRoute } from '@tanstack/react-router';
import { PortalUploadPage } from '@/features/portal/components/PortalUploadPage';

export const Route = createFileRoute('/portal/upload')({
  component: PortalUploadPage,
});
