import { createFileRoute } from '@tanstack/react-router';
import { DLPAdminPage } from '@/features/admin/dlp';

export const Route = createFileRoute('/admin/dlp')({
  component: DLPAdminPage,
});
