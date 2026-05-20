/**
 * DeadlinesPage - Fristen-Übersicht
 *
 * Liste aller Fristen mit Kalender-Export
 */

import * as React from 'react';
import { useParams, useSearch } from '@tanstack/react-router';
import { DeadlineList } from '../components/deadlines/DeadlineList';
import { DeadlineCreateDialog } from '../components/deadlines/DeadlineCreateDialog';
import { DeadlineEditDialog } from '../components/deadlines/DeadlineEditDialog';
import * as privatApi from '../api/privat-api';
import { useDefaultSpace } from '../hooks/use-privat-queries';
import type {
  PrivatDeadlineWithStatus,
  PrivatDeadlineType,
  PrivatDeadlineCreate,
  PrivatDeadlineUpdate,
} from '@/types/privat';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { toast } from 'sonner';

interface DeadlinesPageProps {
  spaceId?: string;
}

export function DeadlinesPage({ spaceId: propSpaceId }: DeadlinesPageProps = {}) {
  const params = useParams({ strict: false }) as { spaceId?: string };
  const search = useSearch({ strict: false }) as { space?: string };
  const { defaultSpaceId, isLoading: isLoadingSpaces, hasSpaces } = useDefaultSpace();

  // Priorität: 1. Props, 2. URL-Params, 3. Query-Param (?space=), 4. Default-Space
  const spaceId = propSpaceId || params.spaceId || search.space || defaultSpaceId;

  const [deadlines, setDeadlines] = React.useState<PrivatDeadlineWithStatus[]>([]);
  const [total, setTotal] = React.useState(0);
  const [page, setPage] = React.useState(0);
  const [searchQuery, setSearchQuery] = React.useState('');
  const [typeFilter, setTypeFilter] = React.useState<PrivatDeadlineType | 'all'>('all');
  const [showCompleted, setShowCompleted] = React.useState(false);
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<Error | null>(null);
  const [deleteDeadline, setDeleteDeadline] = React.useState<PrivatDeadlineWithStatus | null>(null);

  // Dialog state
  const [showCreateDialog, setShowCreateDialog] = React.useState(false);
  const [editDeadline, setEditDeadline] = React.useState<PrivatDeadlineWithStatus | null>(null);
  const [isSubmitting, setIsSubmitting] = React.useState(false);

  const pageSize = 20;

  // Load deadlines
  React.useEffect(() => {
    const loadDeadlines = async () => {
      // Warte auf Spaces wenn noch keine spaceId vorhanden
      if (isLoadingSpaces && !spaceId) {
        return;
      }

      if (!spaceId) {
        if (!hasSpaces) {
          setError(new Error('Noch keine Bereiche vorhanden. Erstellen Sie zuerst einen persönlichen Bereich.'));
        } else {
          setError(new Error('Kein Bereich ausgewählt'));
        }
        setIsLoading(false);
        return;
      }

      setIsLoading(true);
      try {
        const response = await privatApi.listDeadlines(spaceId, {
          page: page + 1,
          pageSize,
          search: searchQuery || undefined,
          deadlineType: typeFilter !== 'all' ? typeFilter : undefined,
          includeCompleted: showCompleted,
        });
        setDeadlines(response.items);
        setTotal(response.total);
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Fehler beim Laden'));
      } finally {
        setIsLoading(false);
      }
    };
    loadDeadlines();
  }, [spaceId, page, searchQuery, typeFilter, showCompleted, isLoadingSpaces, hasSpaces]);

  const handleSelectDeadline = (deadline: PrivatDeadlineWithStatus) => {
    setEditDeadline(deadline);
  };

  const handleCreateDeadline = () => {
    setShowCreateDialog(true);
  };

  const handleEditDeadline = (deadline: PrivatDeadlineWithStatus) => {
    setEditDeadline(deadline);
  };

  const handleCreateSubmit = async (data: PrivatDeadlineCreate) => {
    if (!spaceId) return;
    setIsSubmitting(true);
    try {
      const newDeadline = await privatApi.createDeadline(spaceId, data);
      setDeadlines((prev) => [newDeadline, ...prev]);
      setTotal((prev) => prev + 1);
      toast.success('Frist erstellt');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleEditSubmit = async (deadlineId: string, data: PrivatDeadlineUpdate) => {
    setIsSubmitting(true);
    try {
      const updated = await privatApi.updateDeadline(deadlineId, data);
      setDeadlines((prev) => prev.map((d) => (d.id === deadlineId ? updated : d)));
      toast.success('Frist aktualisiert');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCompleteDeadline = async (deadline: PrivatDeadlineWithStatus) => {
    if (!spaceId) return;

    try {
      await privatApi.completeDeadline(deadline.id);
      setDeadlines((prev) =>
        prev.map((d) =>
          d.id === deadline.id
            ? { ...d, isCompleted: true, completedAt: new Date().toISOString() }
            : d
        )
      );
      toast.success('Frist als erledigt markiert');
    } catch (err) {
      toast.error('Fehler beim Markieren der Frist');
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteDeadline || !spaceId) return;

    try {
      await privatApi.deleteDeadline(deleteDeadline.id);
      setDeadlines((prev) => prev.filter((d) => d.id !== deleteDeadline.id));
      setTotal((prev) => prev - 1);
      toast.success('Frist gelöscht');
    } catch (err) {
      toast.error('Fehler beim Löschen der Frist');
    } finally {
      setDeleteDeadline(null);
    }
  };

  const handleExportCalendar = async () => {
    if (!spaceId) return;

    try {
      const calendarUrl = privatApi.getCalendarExportUrl(spaceId);

      // Create a download link
      const a = document.createElement('a');
      a.href = calendarUrl;
      a.download = 'privat-fristen.ics';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);

      toast.success('Kalender exportiert');
    } catch (err) {
      toast.error('Fehler beim Kalender-Export');
    }
  };

  const handleSearch = (query: string) => {
    setSearchQuery(query);
    setPage(0);
  };

  const handleTypeFilter = (type: PrivatDeadlineType | 'all') => {
    setTypeFilter(type);
    setPage(0);
  };

  const handleShowCompleted = (show: boolean) => {
    setShowCompleted(show);
    setPage(0);
  };

  return (
    <div className="p-8">
      <DeadlineList
        deadlines={deadlines}
        total={total}
        page={page}
        pageSize={pageSize}
        isLoading={isLoading}
        error={error}
        onPageChange={setPage}
        onSelect={handleSelectDeadline}
        onCreate={handleCreateDeadline}
        onEdit={handleEditDeadline}
        onComplete={handleCompleteDeadline}
        onDelete={setDeleteDeadline}
        onExportCalendar={handleExportCalendar}
        onSearch={handleSearch}
        onTypeFilter={handleTypeFilter}
        onShowCompleted={handleShowCompleted}
        selectedType={typeFilter}
        searchQuery={searchQuery}
        showCompleted={showCompleted}
      />

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteDeadline} onOpenChange={(open) => !open && setDeleteDeadline(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Frist löschen</AlertDialogTitle>
            <AlertDialogDescription>
              Möchten Sie die Frist "{deleteDeadline?.title}" wirklich löschen?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfirm}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Löschen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Create Dialog */}
      <DeadlineCreateDialog
        open={showCreateDialog}
        onOpenChange={setShowCreateDialog}
        onSubmit={handleCreateSubmit}
        isLoading={isSubmitting}
      />

      {/* Edit Dialog */}
      <DeadlineEditDialog
        open={!!editDeadline}
        onOpenChange={(open) => !open && setEditDeadline(null)}
        deadline={editDeadline}
        onSubmit={handleEditSubmit}
        isLoading={isSubmitting}
      />
    </div>
  );
}

export default DeadlinesPage;
