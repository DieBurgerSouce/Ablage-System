import { createFileRoute } from '@tanstack/react-router';
import { RulesAdminPage } from '@/features/admin/rules';

export const Route = createFileRoute('/admin/rules')({
  component: RulesAdminPage,
});
