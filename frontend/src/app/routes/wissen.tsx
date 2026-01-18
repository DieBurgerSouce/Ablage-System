/**
 * Wissen Route - Knowledge Management
 *
 * Wissensmanagement mit Notizen und Checklisten.
 */

import { createFileRoute } from '@tanstack/react-router';
import { KnowledgePage } from '@/features/knowledge';

export const Route = createFileRoute('/wissen')({
  component: KnowledgePage,
});
