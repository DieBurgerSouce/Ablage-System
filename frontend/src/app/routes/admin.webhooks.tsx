import { createFileRoute } from '@tanstack/react-router';
import { WebhooksPage } from '@/features/admin/webhooks';

export const Route = createFileRoute('/admin/webhooks')({
    component: WebhooksPage,
});
