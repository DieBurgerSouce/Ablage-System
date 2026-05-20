/**
 * Vorlagen Route
 *
 * Dokumenten-Vorlagen mit Jinja2-Syntax und Ein-Klick Dokumentenerstellung.
 */

import { createFileRoute } from '@tanstack/react-router';
import { TemplatesPage } from '@/features/templates';

export const Route = createFileRoute('/vorlagen')({
  component: TemplatesPage,
});
