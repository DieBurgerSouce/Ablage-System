/**
 * NoteFormDialog - Dialog zum Erstellen/Bearbeiten von Notizen
 */

import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { X, Plus, Loader2 } from 'lucide-react';
import type {
  KnowledgeNote,
  KnowledgeNoteCreate,
  KnowledgeNoteUpdate,
  NoteType,
  ContentFormat,
} from '../types/knowledge-types';
import { NOTE_TYPE_LABELS } from '../types/knowledge-types';

interface NoteFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  note: KnowledgeNote | null;
  onSubmit: (data: KnowledgeNoteCreate | KnowledgeNoteUpdate) => Promise<void>;
  isLoading?: boolean;
}

const NOTE_TYPES: NoteType[] = ['general', 'procedure', 'faq', 'template', 'meeting_notes', 'decision'];
const CONTENT_FORMATS: ContentFormat[] = ['markdown', 'html', 'plain'];

export function NoteFormDialog({
  open,
  onOpenChange,
  note,
  onSubmit,
  isLoading = false,
}: NoteFormDialogProps) {
  const isEdit = !!note;

  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [noteType, setNoteType] = useState<NoteType>('general');
  const [contentFormat, setContentFormat] = useState<ContentFormat>('markdown');
  const [isPinned, setIsPinned] = useState(false);
  const [isTemplate, setIsTemplate] = useState(false);
  const [tags, setTags] = useState<string[]>([]);
  const [newTag, setNewTag] = useState('');

  // Initialisiere Form bei Oeffnen
  useEffect(() => {
    if (open) {
      if (note) {
        setTitle(note.title);
        setContent(note.content || '');
        setNoteType(note.note_type);
        setContentFormat(note.content_format);
        setIsPinned(note.is_pinned);
        setIsTemplate(note.is_template);
        setTags(note.tags);
      } else {
        setTitle('');
        setContent('');
        setNoteType('general');
        setContentFormat('markdown');
        setIsPinned(false);
        setIsTemplate(false);
        setTags([]);
      }
      setNewTag('');
    }
  }, [open, note]);

  const handleAddTag = () => {
    const trimmedTag = newTag.trim().toLowerCase();
    if (trimmedTag && !tags.includes(trimmedTag)) {
      setTags([...tags, trimmedTag]);
      setNewTag('');
    }
  };

  const handleRemoveTag = (tagToRemove: string) => {
    setTags(tags.filter((tag) => tag !== tagToRemove));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!title.trim()) return;

    const data: KnowledgeNoteCreate | KnowledgeNoteUpdate = {
      title: title.trim(),
      content: content || undefined,
      note_type: noteType,
      content_format: contentFormat,
      is_pinned: isPinned,
      is_template: isTemplate,
      tags,
    };

    await onSubmit(data);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{isEdit ? 'Notiz bearbeiten' : 'Neue Notiz erstellen'}</DialogTitle>
            <DialogDescription>
              {isEdit
                ? 'Bearbeiten Sie die Notiz und speichern Sie die Aenderungen.'
                : 'Erstellen Sie eine neue Notiz fuer Ihr Wissensmanagement.'}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {/* Titel */}
            <div className="space-y-2">
              <Label htmlFor="title">Titel *</Label>
              <Input
                id="title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Titel der Notiz"
                required
              />
            </div>

            {/* Typ und Format */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="noteType">Typ</Label>
                <Select value={noteType} onValueChange={(v) => setNoteType(v as NoteType)}>
                  <SelectTrigger id="noteType">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {NOTE_TYPES.map((type) => (
                      <SelectItem key={type} value={type}>
                        {NOTE_TYPE_LABELS[type]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="contentFormat">Format</Label>
                <Select
                  value={contentFormat}
                  onValueChange={(v) => setContentFormat(v as ContentFormat)}
                >
                  <SelectTrigger id="contentFormat">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CONTENT_FORMATS.map((format) => (
                      <SelectItem key={format} value={format}>
                        {format === 'markdown' ? 'Markdown' : format === 'html' ? 'HTML' : 'Text'}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Inhalt */}
            <div className="space-y-2">
              <Label htmlFor="content">Inhalt</Label>
              <Textarea
                id="content"
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder={
                  contentFormat === 'markdown'
                    ? '# Ueberschrift\n\nSchreiben Sie hier Ihren Inhalt in Markdown...'
                    : 'Schreiben Sie hier Ihren Inhalt...'
                }
                rows={10}
                className="font-mono text-sm"
              />
            </div>

            {/* Tags */}
            <div className="space-y-2">
              <Label>Tags</Label>
              <div className="flex flex-wrap gap-2 mb-2">
                {tags.map((tag) => (
                  <Badge key={tag} variant="secondary" className="gap-1">
                    {tag}
                    <button
                      type="button"
                      onClick={() => handleRemoveTag(tag)}
                      className="ml-1 hover:text-destructive"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))}
              </div>
              <div className="flex gap-2">
                <Input
                  value={newTag}
                  onChange={(e) => setNewTag(e.target.value)}
                  placeholder="Neuen Tag hinzufuegen"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      handleAddTag();
                    }
                  }}
                />
                <Button type="button" variant="outline" onClick={handleAddTag}>
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {/* Optionen */}
            <div className="flex items-center gap-8">
              <div className="flex items-center gap-2">
                <Switch
                  id="isPinned"
                  checked={isPinned}
                  onCheckedChange={setIsPinned}
                />
                <Label htmlFor="isPinned">Anpinnen</Label>
              </div>
              <div className="flex items-center gap-2">
                <Switch
                  id="isTemplate"
                  checked={isTemplate}
                  onCheckedChange={setIsTemplate}
                />
                <Label htmlFor="isTemplate">Als Vorlage speichern</Label>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={isLoading || !title.trim()}>
              {isLoading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              {isEdit ? 'Speichern' : 'Erstellen'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
