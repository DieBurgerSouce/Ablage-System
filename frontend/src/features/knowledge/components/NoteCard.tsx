/**
 * NoteCard - Einzelne Notiz-Karte
 *
 * Zeigt eine Notiz mit Titel, Vorschau und Metadaten.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  FileText,
  MoreVertical,
  Pin,
  Edit,
  Trash2,
  Eye,
  Copy,
  Link2,
  FileCheck,
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';
import type { KnowledgeNote, NoteType } from '../types/knowledge-types';
import { NOTE_TYPE_LABELS } from '../types/knowledge-types';
import { cn } from '@/lib/utils';

interface NoteCardProps {
  note: KnowledgeNote;
  onView: (note: KnowledgeNote) => void;
  onEdit: (note: KnowledgeNote) => void;
  onDelete: (note: KnowledgeNote) => void;
  onDuplicate?: (note: KnowledgeNote) => void;
}

const NOTE_TYPE_ICONS: Record<NoteType, React.ReactNode> = {
  general: <FileText className="h-4 w-4" />,
  procedure: <FileCheck className="h-4 w-4" />,
  faq: <FileText className="h-4 w-4" />,
  template: <Copy className="h-4 w-4" />,
  meeting_notes: <FileText className="h-4 w-4" />,
  decision: <FileText className="h-4 w-4" />,
};

const NOTE_TYPE_COLORS: Record<NoteType, string> = {
  general: 'bg-slate-500',
  procedure: 'bg-blue-500',
  faq: 'bg-green-500',
  template: 'bg-purple-500',
  meeting_notes: 'bg-orange-500',
  decision: 'bg-red-500',
};

export function NoteCard({ note, onView, onEdit, onDelete, onDuplicate }: NoteCardProps) {
  // Extrahiere Vorschau aus Content (erste 150 Zeichen)
  const contentPreview = note.content
    ? note.content.replace(/[#*_`]/g, '').slice(0, 150) + (note.content.length > 150 ? '...' : '')
    : 'Kein Inhalt';

  const hasLinks =
    note.linked_document_id || note.linked_entity_id || note.linked_company_id;

  return (
    <Card
      className={cn(
        'hover:shadow-md transition-shadow cursor-pointer group',
        note.is_pinned && 'border-yellow-500 border-2'
      )}
      onClick={() => onView(note)}
    >
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2 flex-1 min-w-0">
            {note.is_pinned && <Pin className="h-4 w-4 text-yellow-500 flex-shrink-0" />}
            <div
              className={cn(
                'p-1.5 rounded',
                NOTE_TYPE_COLORS[note.note_type],
                'text-white flex-shrink-0'
              )}
            >
              {NOTE_TYPE_ICONS[note.note_type]}
            </div>
            <CardTitle className="text-base truncate">{note.title}</CardTitle>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <MoreVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation();
                  onView(note);
                }}
              >
                <Eye className="h-4 w-4 mr-2" />
                Anzeigen
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation();
                  onEdit(note);
                }}
              >
                <Edit className="h-4 w-4 mr-2" />
                Bearbeiten
              </DropdownMenuItem>
              {onDuplicate && (
                <DropdownMenuItem
                  onClick={(e) => {
                    e.stopPropagation();
                    onDuplicate(note);
                  }}
                >
                  <Copy className="h-4 w-4 mr-2" />
                  Duplizieren
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(note);
                }}
                className="text-destructive"
              >
                <Trash2 className="h-4 w-4 mr-2" />
                Loeschen
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        <CardDescription className="flex items-center gap-2 text-xs">
          <span>{NOTE_TYPE_LABELS[note.note_type]}</span>
          {note.is_template && (
            <Badge variant="outline" className="text-xs">
              Vorlage
            </Badge>
          )}
          {hasLinks && <Link2 className="h-3 w-3 text-muted-foreground" />}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground line-clamp-2">{contentPreview}</p>
        <div className="flex items-center justify-between mt-3">
          <div className="flex flex-wrap gap-1">
            {note.tags.slice(0, 3).map((tag) => (
              <Badge key={tag} variant="secondary" className="text-xs">
                {tag}
              </Badge>
            ))}
            {note.tags.length > 3 && (
              <Badge variant="secondary" className="text-xs">
                +{note.tags.length - 3}
              </Badge>
            )}
          </div>
          <span className="text-xs text-muted-foreground">
            {formatDistanceToNow(new Date(note.updated_at), {
              addSuffix: true,
              locale: de,
            })}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
