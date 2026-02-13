/**
 * Knowledge Graph Route
 * Route-Definition für die Wissens-Graph-Seite
 */

import { createFileRoute } from '@tanstack/react-router';
import { KnowledgeGraphPage } from '@/features/knowledge-graph';

export const Route = createFileRoute('/knowledge-graph')({
  component: KnowledgeGraphRoute,
});

function KnowledgeGraphRoute() {
  return <KnowledgeGraphPage />;
}
