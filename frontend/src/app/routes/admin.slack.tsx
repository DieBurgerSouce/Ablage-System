import { createFileRoute } from '@tanstack/react-router';
import { SlackSettingsPage } from '@/features/slack';

export const Route = createFileRoute('/admin/slack')({
    component: SlackSettingsPage,
});
