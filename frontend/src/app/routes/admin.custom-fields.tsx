import { createFileRoute } from '@tanstack/react-router';
import { CustomFieldsPage } from '@/features/admin/custom-fields';

export const Route = createFileRoute('/admin/custom-fields')({
  component: CustomFieldsPage,
});
