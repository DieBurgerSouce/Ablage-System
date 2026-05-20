/**
 * Admin Approval Rules Route
 * Path: /admin/approval-rules
 */

import { createFileRoute } from '@tanstack/react-router';
import { ApprovalRulesPage } from '@/features/approval-enhanced';

export const Route = createFileRoute('/admin/approval-rules')({
  component: ApprovalRulesPage,
});
