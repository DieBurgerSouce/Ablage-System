/**
 * KI-Pipeline Learning Profiles Route
 * Learning profiles page at /ki-pipeline/learning
 */

import { createFileRoute } from '@tanstack/react-router';
import { LearningProfilesPage } from '@/features/ki-pipeline';

export const Route = createFileRoute('/ki-pipeline/learning')({
  component: LearningProfilesPage,
});
