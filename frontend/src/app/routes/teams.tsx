import { createFileRoute } from '@tanstack/react-router';
import { TeamsPage } from '@/features/teams';

export const Route = createFileRoute('/teams')({
  component: TeamsPage,
});
