/**
 * Ad-Hoc Reporting View Route
 * German Enterprise Document Platform
 */

import { createFileRoute } from '@tanstack/react-router';
import { ReportViewPage } from '@/features/adhoc-reporting';

interface ReportViewSearch {
  action?: 'share' | 'export' | 'schedule';
}

export const Route = createFileRoute('/adhoc-reporting/$id')({
  component: ReportViewPage,
  validateSearch: (search: Record<string, unknown>): ReportViewSearch => {
    return {
      action: search.action as 'share' | 'export' | 'schedule' | undefined,
    };
  },
});
