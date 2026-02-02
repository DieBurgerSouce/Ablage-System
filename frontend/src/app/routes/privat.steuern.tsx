/**
 * Steueroptimierung Route
 *
 * Route: /privat/steuern
 *
 * Features:
 * - Absetzbare Beträge nach Kategorie (§9, §10, §33, §35a EStG)
 * - Absetzbarkeits-Checker
 * - Fristen-Kalender
 * - DATEV-Export
 */

import { createFileRoute } from '@tanstack/react-router';
import { SteuerPage } from '@/features/privat/steuern/SteuerPage';

export const Route = createFileRoute('/privat/steuern')({
  component: SteuerPage,
});
