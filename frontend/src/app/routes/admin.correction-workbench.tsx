/**
 * Admin Correction Workbench Route
 * Route fuer die OCR-Korrektur-Workbench
 */

import { createFileRoute } from '@tanstack/react-router';
import { CorrectionWorkbenchPage } from '@/features/admin/correction-workbench';

export const Route = createFileRoute('/admin/correction-workbench')({
  component: CorrectionWorkbenchPage,
});
