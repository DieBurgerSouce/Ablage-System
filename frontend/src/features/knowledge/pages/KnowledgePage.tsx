/**
 * KnowledgePage - Hauptseite fuer das Wissensmanagement
 *
 * Features:
 * - Wiki-artige Notizen
 * - Checklisten
 * - Tag-basierte Kategorisierung
 * - Suche und Filter
 */

import { useState, useCallback } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
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
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import {
  BookOpen,
  Search,
  Plus,
  RefreshCw,
  FileText,
  CheckSquare,
  Tag,
  Pin,
  AlertTriangle,
} from 'lucide-react';
import type {
  KnowledgeNote,
  KnowledgeNoteCreate,
  KnowledgeNoteUpdate,
  KnowledgeNoteListParams,
  KnowledgeChecklist,
  KnowledgeChecklistCreate,
  KnowledgeChecklistUpdate,
  KnowledgeChecklistListParams,
  NoteType,
} from '../types/knowledge-types';
import { NOTE_TYPE_LABELS } from '../types/knowledge-types';
import {
  useNotes,
  useNote,
  useCreateNote,
  useUpdateNote,
  useDeleteNote,
  useChecklists,
  useCreateChecklist,
  useUpdateChecklist,
  useDeleteChecklist,
  useUpdateChecklistItem,
  useTags,
} from '../api/knowledge-api';
import { NoteCard } from '../components/NoteCard';
import { NoteFormDialog } from '../components/NoteFormDialog';
import { NoteDetailSheet } from '../components/NoteDetailSheet';
import { ChecklistCard } from '../components/ChecklistCard';
import { ChecklistFormDialog } from '../components/ChecklistFormDialog';

const DEFAULT_PAGE_SIZE = 20;
const NOTE_TYPES: Array<NoteType | 'all'> = ['all', 'general', 'procedure', 'faq', 'template', 'meeting_notes', 'decision'];

export function KnowledgePage() {
  // Tab state
  const [activeTab, setActiveTab] = useState<'notes' | 'checklists'>('notes');

  // Notes filter state
  const [noteFilters, setNoteFilters] = useState<KnowledgeNoteListParams>({
    offset: 0,
    limit: DEFAULT_PAGE_SIZE,
  });
  const [noteSearch, setNoteSearch] = useState('');
  const [noteTypeFilter, setNoteTypeFilter] = useState<NoteType | 'all'>('all');
  const [showPinnedOnly, setShowPinnedOnly] = useState(false);

  // Checklists filter state
  const [checklistFilters, setChecklistFilters] = useState<KnowledgeChecklistListParams>({
    offset: 0,
    limit: DEFAULT_PAGE_SIZE,
  });
  const [checklistSearch, setChecklistSearch] = useState('');

  // UI state
  const [selectedNoteId, setSelectedNoteId] = useState<string | null>(null);
  const [noteDetailOpen, setNoteDetailOpen] = useState(false);
  const [noteFormOpen, setNoteFormOpen] = useState(false);
  const [editNote, setEditNote] = useState<KnowledgeNote | null>(null);
  const [deleteNote, setDeleteNote] = useState<KnowledgeNote | null>(null);
  const [checklistFormOpen, setChecklistFormOpen] = useState(false);
  const [editChecklist, setEditChecklist] = useState<KnowledgeChecklist | null>(null);
  const [deleteChecklist, setDeleteChecklist] = useState<KnowledgeChecklist | null>(null);

  // Build note filters
  const effectiveNoteFilters: KnowledgeNoteListParams = {
    ...noteFilters,
    search: noteSearch || undefined,
    note_type: noteTypeFilter !== 'all' ? noteTypeFilter : undefined,
    is_pinned: showPinnedOnly ? true : undefined,
  };

  // Build checklist filters
  const effectiveChecklistFilters: KnowledgeChecklistListParams = {
    ...checklistFilters,
    search: checklistSearch || undefined,
  };

  // Queries
  const {
    data: notesData,
    isLoading: isLoadingNotes,
    isError: isNotesError,
    refetch: refetchNotes,
    isFetching: isFetchingNotes,
  } = useNotes(effectiveNoteFilters);

  const {
    data: checklistsData,
    isLoading: isLoadingChecklists,
    isError: isChecklistsError,
    refetch: refetchChecklists,
    isFetching: isFetchingChecklists,
  } = useChecklists(effectiveChecklistFilters);

  const { data: tagsData } = useTags({ limit: 50 });

  const {
    data: selectedNote,
    isLoading: isLoadingSelectedNote,
  } = useNote(selectedNoteId || '', { enabled: !!selectedNoteId });

  // Mutations
  const createNoteMutation = useCreateNote();
  const updateNoteMutation = useUpdateNote();
  const deleteNoteMutation = useDeleteNote();
  const createChecklistMutation = useCreateChecklist();
  const updateChecklistMutation = useUpdateChecklist();
  const deleteChecklistMutation = useDeleteChecklist();
  const updateChecklistItemMutation = useUpdateChecklistItem();

  // Handlers - Notes
  const handleViewNote = useCallback((note: KnowledgeNote) => {
    setSelectedNoteId(note.id);
    setNoteDetailOpen(true);
  }, []);

  const handleEditNote = useCallback((note: KnowledgeNote) => {
    setEditNote(note);
    setNoteFormOpen(true);
  }, []);

  const handleCreateNote = useCallback(() => {
    setEditNote(null);
    setNoteFormOpen(true);
  }, []);

  const handleNoteFormSubmit = async (data: KnowledgeNoteCreate | KnowledgeNoteUpdate) => {
    try {
      if (editNote) {
        await updateNoteMutation.mutateAsync({ id: editNote.id, data: data as KnowledgeNoteUpdate });
        toast.success('Notiz aktualisiert');
      } else {
        await createNoteMutation.mutateAsync(data as KnowledgeNoteCreate);
        toast.success('Notiz erstellt');
      }
      setNoteFormOpen(false);
      setEditNote(null);
    } catch (error) {
      toast.error(editNote ? 'Fehler beim Aktualisieren' : 'Fehler beim Erstellen');
      throw error;
    }
  };

  const handleDeleteNoteConfirm = async () => {
    if (!deleteNote) return;
    try {
      await deleteNoteMutation.mutateAsync(deleteNote.id);
      toast.success('Notiz geloescht');
      setDeleteNote(null);
      setNoteDetailOpen(false);
    } catch (error) {
      toast.error('Fehler beim Loeschen der Notiz');
    }
  };

  // Handlers - Checklists
  const handleEditChecklist = useCallback((checklist: KnowledgeChecklist) => {
    setEditChecklist(checklist);
    setChecklistFormOpen(true);
  }, []);

  const handleCreateChecklist = useCallback(() => {
    setEditChecklist(null);
    setChecklistFormOpen(true);
  }, []);

  const handleChecklistFormSubmit = async (data: KnowledgeChecklistCreate | KnowledgeChecklistUpdate) => {
    try {
      if (editChecklist) {
        await updateChecklistMutation.mutateAsync({
          id: editChecklist.id,
          data: data as KnowledgeChecklistUpdate,
        });
        toast.success('Checkliste aktualisiert');
      } else {
        await createChecklistMutation.mutateAsync(data as KnowledgeChecklistCreate);
        toast.success('Checkliste erstellt');
      }
      setChecklistFormOpen(false);
      setEditChecklist(null);
    } catch (error) {
      toast.error(editChecklist ? 'Fehler beim Aktualisieren' : 'Fehler beim Erstellen');
      throw error;
    }
  };

  const handleDeleteChecklistConfirm = async () => {
    if (!deleteChecklist) return;
    try {
      await deleteChecklistMutation.mutateAsync(deleteChecklist.id);
      toast.success('Checkliste geloescht');
      setDeleteChecklist(null);
    } catch (error) {
      toast.error('Fehler beim Loeschen der Checkliste');
    }
  };

  const handleToggleChecklistItem = async (
    checklistId: string,
    itemId: string,
    isCompleted: boolean
  ) => {
    try {
      await updateChecklistItemMutation.mutateAsync({
        checklistId,
        itemId,
        data: { is_completed: isCompleted },
      });
    } catch (error) {
      toast.error('Fehler beim Aktualisieren');
    }
  };

  // Pagination
  const noteCurrentPage = Math.floor((noteFilters.offset || 0) / DEFAULT_PAGE_SIZE);
  const noteTotalPages = Math.ceil((notesData?.total || 0) / DEFAULT_PAGE_SIZE);

  const checklistCurrentPage = Math.floor((checklistFilters.offset || 0) / DEFAULT_PAGE_SIZE);
  const checklistTotalPages = Math.ceil((checklistsData?.total || 0) / DEFAULT_PAGE_SIZE);

  const handleNotePageChange = (newPage: number) => {
    setNoteFilters((prev) => ({ ...prev, offset: newPage * DEFAULT_PAGE_SIZE }));
  };

  const handleChecklistPageChange = (newPage: number) => {
    setChecklistFilters((prev) => ({ ...prev, offset: newPage * DEFAULT_PAGE_SIZE }));
  };

  // Error state
  if (isNotesError || isChecklistsError) {
    return (
      <Card className="m-8">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="h-5 w-5" />
            Fehler beim Laden
          </CardTitle>
          <CardDescription>
            Die Wissensdaten konnten nicht geladen werden. Bitte versuchen Sie es erneut.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            onClick={() => {
              refetchNotes();
              refetchChecklists();
            }}
            variant="outline"
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            Erneut versuchen
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <BookOpen className="h-6 w-6" />
            Wissensmanagement
          </h1>
          <p className="text-muted-foreground">
            Verwalten Sie Notizen, Checklisten und Wissen
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            if (activeTab === 'notes') refetchNotes();
            else refetchChecklists();
          }}
          disabled={isFetchingNotes || isFetchingChecklists}
        >
          <RefreshCw
            className={`h-4 w-4 mr-2 ${isFetchingNotes || isFetchingChecklists ? 'animate-spin' : ''}`}
          />
          Aktualisieren
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Notizen</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{notesData?.total || 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Checklisten</CardTitle>
            <CheckSquare className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{checklistsData?.total || 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Tags</CardTitle>
            <Tag className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{tagsData?.total || 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Angepinnt</CardTitle>
            <Pin className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {notesData?.items.filter((n) => n.is_pinned).length || 0}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Main Content */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'notes' | 'checklists')}>
        <div className="flex items-center justify-between mb-4">
          <TabsList>
            <TabsTrigger value="notes" className="flex items-center gap-2">
              <FileText className="h-4 w-4" />
              Notizen
            </TabsTrigger>
            <TabsTrigger value="checklists" className="flex items-center gap-2">
              <CheckSquare className="h-4 w-4" />
              Checklisten
            </TabsTrigger>
          </TabsList>

          <Button onClick={activeTab === 'notes' ? handleCreateNote : handleCreateChecklist}>
            <Plus className="h-4 w-4 mr-2" />
            {activeTab === 'notes' ? 'Neue Notiz' : 'Neue Checkliste'}
          </Button>
        </div>

        {/* Notes Tab */}
        <TabsContent value="notes" className="space-y-4">
          {/* Filters */}
          <Card>
            <CardContent className="pt-4">
              <div className="flex flex-wrap gap-4">
                <div className="flex-1 min-w-[200px]">
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      placeholder="Notizen suchen..."
                      value={noteSearch}
                      onChange={(e) => setNoteSearch(e.target.value)}
                      className="pl-9"
                    />
                  </div>
                </div>
                <Select
                  value={noteTypeFilter}
                  onValueChange={(v) => setNoteTypeFilter(v as NoteType | 'all')}
                >
                  <SelectTrigger className="w-[180px]">
                    <SelectValue placeholder="Typ waehlen" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Alle Typen</SelectItem>
                    {NOTE_TYPES.filter((t) => t !== 'all').map((type) => (
                      <SelectItem key={type} value={type}>
                        {NOTE_TYPE_LABELS[type as NoteType]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  variant={showPinnedOnly ? 'default' : 'outline'}
                  onClick={() => setShowPinnedOnly(!showPinnedOnly)}
                >
                  <Pin className="h-4 w-4 mr-2" />
                  Nur Angepinnte
                </Button>
              </div>

              {/* Active Tags */}
              {tagsData && tagsData.items.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-4">
                  {tagsData.items.slice(0, 10).map((tag) => (
                    <Badge
                      key={tag.id}
                      variant="secondary"
                      className="cursor-pointer hover:bg-primary hover:text-primary-foreground"
                      onClick={() => setNoteSearch(tag.name)}
                    >
                      {tag.name} ({tag.usage_count})
                    </Badge>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Notes Grid */}
          {isLoadingNotes ? (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {[1, 2, 3, 4, 5, 6].map((i) => (
                <Card key={i}>
                  <CardHeader>
                    <Skeleton className="h-5 w-3/4" />
                    <Skeleton className="h-4 w-1/2" />
                  </CardHeader>
                  <CardContent>
                    <Skeleton className="h-12 w-full" />
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : notesData && notesData.items.length > 0 ? (
            <>
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {notesData.items.map((note) => (
                  <NoteCard
                    key={note.id}
                    note={note}
                    onView={handleViewNote}
                    onEdit={handleEditNote}
                    onDelete={setDeleteNote}
                  />
                ))}
              </div>

              {/* Pagination */}
              {noteTotalPages > 1 && (
                <div className="flex items-center justify-between">
                  <p className="text-sm text-muted-foreground">
                    Seite {noteCurrentPage + 1} von {noteTotalPages} ({notesData.total} Notizen)
                  </p>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleNotePageChange(noteCurrentPage - 1)}
                      disabled={noteCurrentPage === 0}
                    >
                      Zurueck
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleNotePageChange(noteCurrentPage + 1)}
                      disabled={noteCurrentPage >= noteTotalPages - 1}
                    >
                      Weiter
                    </Button>
                  </div>
                </div>
              )}
            </>
          ) : (
            <Card>
              <CardContent className="py-12 text-center">
                <FileText className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                <h3 className="text-lg font-medium mb-2">Keine Notizen gefunden</h3>
                <p className="text-muted-foreground mb-4">
                  Erstellen Sie Ihre erste Notiz, um Wissen zu dokumentieren.
                </p>
                <Button onClick={handleCreateNote}>
                  <Plus className="h-4 w-4 mr-2" />
                  Erste Notiz erstellen
                </Button>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Checklists Tab */}
        <TabsContent value="checklists" className="space-y-4">
          {/* Filters */}
          <Card>
            <CardContent className="pt-4">
              <div className="flex gap-4">
                <div className="flex-1">
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      placeholder="Checklisten suchen..."
                      value={checklistSearch}
                      onChange={(e) => setChecklistSearch(e.target.value)}
                      className="pl-9"
                    />
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Checklists Grid */}
          {isLoadingChecklists ? (
            <div className="grid gap-4 md:grid-cols-2">
              {[1, 2, 3, 4].map((i) => (
                <Card key={i}>
                  <CardHeader>
                    <Skeleton className="h-5 w-3/4" />
                    <Skeleton className="h-4 w-1/2" />
                  </CardHeader>
                  <CardContent>
                    <Skeleton className="h-24 w-full" />
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : checklistsData && checklistsData.items.length > 0 ? (
            <>
              <div className="grid gap-4 md:grid-cols-2">
                {checklistsData.items.map((checklist) => (
                  <ChecklistCard
                    key={checklist.id}
                    checklist={checklist}
                    onEdit={handleEditChecklist}
                    onDelete={setDeleteChecklist}
                    onToggleItem={handleToggleChecklistItem}
                  />
                ))}
              </div>

              {/* Pagination */}
              {checklistTotalPages > 1 && (
                <div className="flex items-center justify-between">
                  <p className="text-sm text-muted-foreground">
                    Seite {checklistCurrentPage + 1} von {checklistTotalPages} (
                    {checklistsData.total} Checklisten)
                  </p>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleChecklistPageChange(checklistCurrentPage - 1)}
                      disabled={checklistCurrentPage === 0}
                    >
                      Zurueck
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleChecklistPageChange(checklistCurrentPage + 1)}
                      disabled={checklistCurrentPage >= checklistTotalPages - 1}
                    >
                      Weiter
                    </Button>
                  </div>
                </div>
              )}
            </>
          ) : (
            <Card>
              <CardContent className="py-12 text-center">
                <CheckSquare className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                <h3 className="text-lg font-medium mb-2">Keine Checklisten gefunden</h3>
                <p className="text-muted-foreground mb-4">
                  Erstellen Sie Ihre erste Checkliste, um Aufgaben zu verwalten.
                </p>
                <Button onClick={handleCreateChecklist}>
                  <Plus className="h-4 w-4 mr-2" />
                  Erste Checkliste erstellen
                </Button>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>

      {/* Note Detail Sheet */}
      <NoteDetailSheet
        note={selectedNote || null}
        open={noteDetailOpen}
        onOpenChange={setNoteDetailOpen}
        onEdit={() => {
          if (selectedNote) {
            handleEditNote(selectedNote as KnowledgeNote);
          }
        }}
        onDelete={() => {
          if (selectedNote) {
            setDeleteNote(selectedNote as KnowledgeNote);
          }
        }}
        isLoading={isLoadingSelectedNote}
      />

      {/* Note Form Dialog */}
      <NoteFormDialog
        open={noteFormOpen}
        onOpenChange={setNoteFormOpen}
        note={editNote}
        onSubmit={handleNoteFormSubmit}
        isLoading={createNoteMutation.isPending || updateNoteMutation.isPending}
      />

      {/* Checklist Form Dialog */}
      <ChecklistFormDialog
        open={checklistFormOpen}
        onOpenChange={setChecklistFormOpen}
        checklist={editChecklist}
        onSubmit={handleChecklistFormSubmit}
        isLoading={createChecklistMutation.isPending || updateChecklistMutation.isPending}
      />

      {/* Delete Note Confirmation */}
      <AlertDialog open={!!deleteNote} onOpenChange={(open) => !open && setDeleteNote(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Notiz loeschen</AlertDialogTitle>
            <AlertDialogDescription>
              Moechten Sie die Notiz "{deleteNote?.title}" wirklich loeschen? Diese Aktion kann
              nicht rueckgaengig gemacht werden.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteNoteConfirm}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Loeschen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete Checklist Confirmation */}
      <AlertDialog
        open={!!deleteChecklist}
        onOpenChange={(open) => !open && setDeleteChecklist(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Checkliste loeschen</AlertDialogTitle>
            <AlertDialogDescription>
              Moechten Sie die Checkliste "{deleteChecklist?.title}" wirklich loeschen? Alle
              Eintraege werden ebenfalls geloescht.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteChecklistConfirm}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Loeschen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

export default KnowledgePage;
