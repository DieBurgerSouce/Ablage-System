/**
 * Admin Mahnungen - Kanban Board
 *
 * Visualisiert Mahnvorgaenge als Kanban-Board nach Eskalationsstufe
 */

import { createFileRoute } from '@tanstack/react-router';
import { MahnKanbanBoard } from '@/features/banking/components/MahnKanbanBoard';

export const Route = createFileRoute('/admin/mahnungen/kanban')({
    component: KanbanPage,
});

function KanbanPage() {
    return <MahnKanbanBoard />;
}
