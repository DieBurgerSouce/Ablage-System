/**
 * Ad-Hoc Reporting Builder Route
 * German Enterprise Document Platform
 */

import { createFileRoute } from '@tanstack/react-router';
import { ReportBuilderPage } from '@/features/adhoc-reporting';

export const Route = createFileRoute('/adhoc-reporting/new')({
  component: ReportBuilderPage,
});
