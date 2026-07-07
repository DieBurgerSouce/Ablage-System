/**
 * Knowledge Graph Route
 * Route-Definition für die Wissens-Graph-Seite
 */

import { createFileRoute } from '@tanstack/react-router';
import { frozenModuleGuard } from '@/lib/frozen-modules';
import { KnowledgeGraphPage } from '@/features/knowledge-graph';

export const Route = createFileRoute('/knowledge-graph')({
  // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts)
  beforeLoad: () => frozenModuleGuard('ai_speculative'),
  component: KnowledgeGraphRoute,
});

function KnowledgeGraphRoute() {
  return <KnowledgeGraphPage />;
}
