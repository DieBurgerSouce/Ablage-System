/**
 * ChecklistFormDialog - Dialog zum Erstellen/Bearbeiten von Checklisten
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
import { Plus, Trash2, Loader2, GripVertical } from 'lucide-react';
import type {
  KnowledgeChecklist,
  KnowledgeChecklistCreate,
  KnowledgeChecklistUpdate,
} from '../types/knowledge-types';

interface ChecklistFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  checklist: KnowledgeChecklist | null;
  onSubmit: (data: KnowledgeChecklistCreate | KnowledgeChecklistUpdate) => Promise<void>;
  isLoading?: boolean;
}

interface ItemInput {
  id: string;
  text: string;
  description: string;
  due_date: string;
}

export function ChecklistFormDialog({
  open,
  onOpenChange,
  checklist,
  onSubmit,
  isLoading = false,
}: ChecklistFormDialogProps) {
  const isEdit = !!checklist;

  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [isTemplate, setIsTemplate] = useState(false);
  const [items, setItems] = useState<ItemInput[]>([]);

  // Initialisiere Form bei Oeffnen
  useEffect(() => {
    if (open) {
      if (checklist) {
        setTitle(checklist.title);
        setDescription(checklist.description || '');
        setIsTemplate(checklist.is_template);
        setItems(
          checklist.items.map((item) => ({
            id: item.id,
            text: item.text,
            description: item.description || '',
            due_date: item.due_date ? item.due_date.split('T')[0] : '',
          }))
        );
      } else {
        setTitle('');
        setDescription('');
        setIsTemplate(false);
        setItems([{ id: crypto.randomUUID(), text: '', description: '', due_date: '' }]);
      }
    }
  }, [open, checklist]);

  const handleAddItem = () => {
    setItems([...items, { id: crypto.randomUUID(), text: '', description: '', due_date: '' }]);
  };

  const handleRemoveItem = (id: string) => {
    if (items.length > 1) {
      setItems(items.filter((item) => item.id !== id));
    }
  };

  const handleItemChange = (id: string, field: keyof ItemInput, value: string) => {
    setItems(items.map((item) => (item.id === id ? { ...item, [field]: value } : item)));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!title.trim()) return;

    // Filtere leere Items
    const validItems = items
      .filter((item) => item.text.trim())
      .map((item, index) => ({
        text: item.text.trim(),
        description: item.description.trim() || undefined,
        due_date: item.due_date || undefined,
        sort_order: index,
      }));

    const data: KnowledgeChecklistCreate | KnowledgeChecklistUpdate = {
      title: title.trim(),
      description: description.trim() || undefined,
      is_template: isTemplate,
      ...(isEdit ? {} : { items: validItems }),
    };

    await onSubmit(data);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>
              {isEdit ? 'Checkliste bearbeiten' : 'Neue Checkliste erstellen'}
            </DialogTitle>
            <DialogDescription>
              {isEdit
                ? 'Bearbeiten Sie die Checkliste und speichern Sie die Aenderungen.'
                : 'Erstellen Sie eine neue Checkliste mit Ihren Aufgaben.'}
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
                placeholder="Titel der Checkliste"
                required
              />
            </div>

            {/* Beschreibung */}
            <div className="space-y-2">
              <Label htmlFor="description">Beschreibung</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optionale Beschreibung"
                rows={2}
              />
            </div>

            {/* Vorlage Option */}
            <div className="flex items-center gap-2">
              <Switch id="isTemplate" checked={isTemplate} onCheckedChange={setIsTemplate} />
              <Label htmlFor="isTemplate">Als Vorlage speichern</Label>
            </div>

            {/* Items (nur bei Erstellung) */}
            {!isEdit && (
              <div className="space-y-2">
                <Label>Eintraege</Label>
                <div className="space-y-3">
                  {items.map((item, index) => (
                    <div key={item.id} className="flex items-start gap-2 p-3 border rounded">
                      <div className="flex items-center justify-center w-6 h-6 text-muted-foreground">
                        <GripVertical className="h-4 w-4" />
                      </div>
                      <div className="flex-1 space-y-2">
                        <Input
                          value={item.text}
                          onChange={(e) => handleItemChange(item.id, 'text', e.target.value)}
                          placeholder={`Eintrag ${index + 1}`}
                        />
                        <div className="grid grid-cols-2 gap-2">
                          <Input
                            value={item.description}
                            onChange={(e) =>
                              handleItemChange(item.id, 'description', e.target.value)
                            }
                            placeholder="Beschreibung (optional)"
                            className="text-sm"
                          />
                          <Input
                            type="date"
                            value={item.due_date}
                            onChange={(e) => handleItemChange(item.id, 'due_date', e.target.value)}
                            className="text-sm"
                          />
                        </div>
                      </div>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={() => handleRemoveItem(item.id)}
                        disabled={items.length <= 1}
                        className="flex-shrink-0"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                </div>
                <Button type="button" variant="outline" onClick={handleAddItem} className="w-full">
                  <Plus className="h-4 w-4 mr-2" />
                  Eintrag hinzufuegen
                </Button>
              </div>
            )}

            {isEdit && (
              <p className="text-sm text-muted-foreground">
                Eintraege koennen nach dem Speichern direkt in der Checkliste bearbeitet werden.
              </p>
            )}
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
