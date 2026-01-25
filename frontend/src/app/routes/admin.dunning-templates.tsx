import { createFileRoute } from '@tanstack/react-router';
import { DunningTemplatesPage } from '@/features/admin/dunning-templates/DunningTemplatesPage';

export const Route = createFileRoute('/admin/dunning-templates')({
  component: DunningTemplatesPage,
});
