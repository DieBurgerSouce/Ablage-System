/**
 * NoteDetailSheet - Seitenpanel fuer Notiz-Details
 */

import DOMPurify from 'dompurify';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Separator } from '@/components/ui/separator';
import {
  Edit,
  Trash2,
  Pin,
  Copy,
  Eye,
  Calendar,
  User,
  Link2,
  FileText,
} from 'lucide-react';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';
import type { KnowledgeNoteDetail } from '../types/knowledge-types';
import { NOTE_TYPE_LABELS } from '../types/knowledge-types';

interface NoteDetailSheetProps {
  note: KnowledgeNoteDetail | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onEdit: () => void;
  onDelete: () => void;
  isLoading?: boolean;
}

export function NoteDetailSheet({
  note,
  open,
  onOpenChange,
  onEdit,
  onDelete,
  isLoading = false,
}: NoteDetailSheetProps) {
  if (isLoading) {
    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent className="w-[600px] sm:max-w-[600px] overflow-y-auto">
          <SheetHeader>
            <Skeleton className="h-6 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
          </SheetHeader>
          <div className="space-y-4 mt-6">
            <Skeleton className="h-32 w-full" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
          </div>
        </SheetContent>
      </Sheet>
    );
  }

  if (!note) return null;

  const formatDate = (dateStr: string) => {
    return format(new Date(dateStr), "d. MMMM yyyy 'um' HH:mm", { locale: de });
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[600px] sm:max-w-[600px] overflow-y-auto">
        <SheetHeader>
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2">
              {note.is_pinned && <Pin className="h-5 w-5 text-yellow-500" />}
              <SheetTitle className="text-xl">{note.title}</SheetTitle>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={onEdit}>
                <Edit className="h-4 w-4 mr-1" />
                Bearbeiten
              </Button>
              <Button variant="destructive" size="sm" onClick={onDelete}>
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          </div>
          <SheetDescription className="flex items-center gap-2 flex-wrap">
            <Badge>{NOTE_TYPE_LABELS[note.note_type]}</Badge>
            {note.is_template && (
              <Badge variant="outline">
                <Copy className="h-3 w-3 mr-1" />
                Vorlage
              </Badge>
            )}
            <span className="flex items-center gap-1 text-xs">
              <Eye className="h-3 w-3" />
              {note.view_count} Aufrufe
            </span>
          </SheetDescription>
        </SheetHeader>

        <div className="mt-6 space-y-6">
          {/* Tags */}
          {note.tags.length > 0 && (
            <div>
              <h4 className="text-sm font-medium mb-2">Tags</h4>
              <div className="flex flex-wrap gap-2">
                {note.tags.map((tag) => (
                  <Badge key={tag} variant="secondary">
                    {tag}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          <Separator />

          {/* Content */}
          <div>
            <h4 className="text-sm font-medium mb-3">Inhalt</h4>
            <div className="prose prose-sm dark:prose-invert max-w-none">
              {note.content_format === 'html' ? (
                <div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(note.content || '<em>Kein Inhalt</em>') }} />
              ) : (
                <pre className="whitespace-pre-wrap font-sans text-sm">{note.content || 'Kein Inhalt'}</pre>
              )}
            </div>
          </div>

          <Separator />

          {/* Verknuepfungen */}
          {(note.linked_document_id || note.linked_entity_id || note.linked_company_id) && (
            <>
              <div>
                <h4 className="text-sm font-medium mb-3 flex items-center gap-2">
                  <Link2 className="h-4 w-4" />
                  Verknuepfungen
                </h4>
                <div className="space-y-2 text-sm">
                  {note.linked_document_id && (
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4 text-muted-foreground" />
                      <span>Dokument: {note.linked_document_id}</span>
                    </div>
                  )}
                  {note.linked_entity_id && (
                    <div className="flex items-center gap-2">
                      <User className="h-4 w-4 text-muted-foreground" />
                      <span>Geschaeftspartner: {note.linked_entity_id}</span>
                    </div>
                  )}
                  {note.linked_company_id && (
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4 text-muted-foreground" />
                      <span>Firma: {note.linked_company_id}</span>
                    </div>
                  )}
                </div>
              </div>
              <Separator />
            </>
          )}

          {/* Knowledge Links */}
          {(note.links_from?.length || note.links_to?.length) && (
            <>
              <div>
                <h4 className="text-sm font-medium mb-3">Verlinkte Inhalte</h4>
                <div className="space-y-2 text-sm">
                  {note.links_from?.map((link) => (
                    <div key={link.id} className="flex items-center gap-2">
                      <Badge variant="outline">{link.link_type}</Badge>
                      <span>
                        {link.target_type}: {link.target_id}
                      </span>
                    </div>
                  ))}
                  {note.links_to?.map((link) => (
                    <div key={link.id} className="flex items-center gap-2">
                      <Badge variant="outline">{link.link_type}</Badge>
                      <span>
                        {link.source_type}: {link.source_id}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
              <Separator />
            </>
          )}

          {/* Kindnotizen */}
          {note.child_notes && note.child_notes.length > 0 && (
            <>
              <div>
                <h4 className="text-sm font-medium mb-3">Unterseiten</h4>
                <div className="space-y-2">
                  {note.child_notes.map((child) => (
                    <div
                      key={child.id}
                      className="flex items-center gap-2 p-2 rounded border hover:bg-muted cursor-pointer"
                    >
                      <FileText className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm">{child.title}</span>
                    </div>
                  ))}
                </div>
              </div>
              <Separator />
            </>
          )}

          {/* Metadaten */}
          <div>
            <h4 className="text-sm font-medium mb-3">Details</h4>
            <div className="space-y-2 text-sm text-muted-foreground">
              <div className="flex items-center gap-2">
                <Calendar className="h-4 w-4" />
                <span>Erstellt: {formatDate(note.created_at)}</span>
              </div>
              <div className="flex items-center gap-2">
                <Calendar className="h-4 w-4" />
                <span>Aktualisiert: {formatDate(note.updated_at)}</span>
              </div>
              {note.parent_note && (
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4" />
                  <span>Uebergeordnete Notiz: {note.parent_note.title}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
