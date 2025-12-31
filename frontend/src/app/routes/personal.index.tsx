/**
 * Personal Index Route
 *
 * Hauptseite für Personal-/Mitarbeiterverwaltung.
 */

import { createFileRoute } from '@tanstack/react-router';
import { PersonalPage } from '@/features/personal';

export const Route = createFileRoute('/personal/')({
  component: PersonalPage,
});
