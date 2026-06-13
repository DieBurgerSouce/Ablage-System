/**
 * Admin Mahnungen - Kanban Board
 *
 * Visualisiert Mahnvorgänge als Kanban-Board nach Eskalationsstufe
 */

import { createFileRoute } from '@tanstack/react-router';
import { lazyRoute } from '@/lib/lazyRoute';

const MahnKanbanBoard = lazyRoute(() => import('@/features/banking/components/MahnKanbanBoard').then(m => ({ default: m.MahnKanbanBoard })));

export const Route = createFileRoute('/admin/mahnungen/kanban')({
    component: KanbanPage,
});

function KanbanPage() {
    return <MahnKanbanBoard />;
}
