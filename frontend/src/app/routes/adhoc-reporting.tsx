/**
 * Ad-Hoc Reporting List Route
 * German Enterprise Document Platform
 */

import { createFileRoute } from '@tanstack/react-router';
import { ReportListPage } from '@/features/adhoc-reporting';

export const Route = createFileRoute('/adhoc-reporting')({
  component: ReportListPage,
});
