/**
 * Admin Mahnungen - Kanban Board
 *
 * Visualisiert Mahnvorgänge als Kanban-Board nach Eskalationsstufe
 */

import { createFileRoute } from '@tanstack/react-router';
import { lazy, Suspense } from 'react';
import { LazyLoadFallback } from '@/components/LazyLoadFallback';

const MahnKanbanBoard = lazy(() => import('@/features/banking/components/MahnKanbanBoard').then(m => ({ default: m.MahnKanbanBoard })));

export const Route = createFileRoute('/admin/mahnungen/kanban')({
    component: KanbanPage,
});

function KanbanPage() {
    return (
        <Suspense fallback={<LazyLoadFallback />}>
            <MahnKanbanBoard />
        </Suspense>
    );
}
