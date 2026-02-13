/**
 * CreateTaskDialog - Dialog zum Erstellen neuer Aufgaben
 *
 * Formular mit Titel, Beschreibung, Prioritaet, Faelligkeit
 * und Benutzer-Zuweisung via Suche.
 */

import { useState, useCallback } from 'react';
import { Loader2 } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { useCreateTask } from '../hooks/use-document-tasks';
import { useUserSearch } from '../hooks/use-user-search';
import type { TaskPriority } from '../api/document-tasks-api';

// ==================== Component ====================

interface CreateTaskDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  documentId: string;
  onCreated?: () => void;
}

export function CreateTaskDialog({
  open,
  onOpenChange,
  documentId,
  onCreated,
}: CreateTaskDialogProps) {
  const createMutation = useCreateTask();

  // Form state
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<TaskPriority>('medium');
  const [dueDate, setDueDate] = useState('');
  const [assigneeId, setAssigneeId] = useState('');
  const [assigneeName, setAssigneeName] = useState('');

  // User search state
  const [userQuery, setUserQuery] = useState('');
  const [userPopoverOpen, setUserPopoverOpen] = useState(false);
  const { users, isLoading: usersLoading } = useUserSearch(userQuery);

  const resetForm = useCallback(() => {
    setTitle('');
    setDescription('');
    setPriority('medium');
    setDueDate('');
    setAssigneeId('');
    setAssigneeName('');
    setUserQuery('');
  }, []);

  const handleSubmit = useCallback(async () => {
    if (!title.trim()) return;

    try {
      await createMutation.mutateAsync({
        document_id: documentId,
        title: title.trim(),
        description: description.trim() || undefined,
        priority,
        assignee_id: assigneeId || undefined,
        due_date: dueDate || undefined,
      });

      resetForm();
      onOpenChange(false);
      onCreated?.();
    } catch {
      // Error handling via toast in the hook
    }
  }, [
    title,
    description,
    priority,
    assigneeId,
    dueDate,
    documentId,
    createMutation,
    resetForm,
    onOpenChange,
    onCreated,
  ]);

  const handleUserSelect = useCallback(
    (userId: string, userName: string) => {
      setAssigneeId(userId);
      setAssigneeName(userName);
      setUserQuery('');
      setUserPopoverOpen(false);
    },
    [],
  );

  const handleClearAssignee = useCallback(() => {
    setAssigneeId('');
    setAssigneeName('');
    setUserQuery('');
  }, []);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Neue Aufgabe erstellen</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Titel */}
          <div className="space-y-2">
            <Label htmlFor="task-title">Titel *</Label>
            <Input
              id="task-title"
              placeholder="Aufgabentitel eingeben..."
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              autoFocus
            />
          </div>

          {/* Beschreibung */}
          <div className="space-y-2">
            <Label htmlFor="task-description">Beschreibung</Label>
            <Textarea
              id="task-description"
              placeholder="Optionale Beschreibung..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
            />
          </div>

          {/* Prioritaet */}
          <div className="space-y-2">
            <Label>Prioritaet</Label>
            <Select value={priority} onValueChange={(v) => setPriority(v as TaskPriority)}>
              <SelectTrigger>
                <SelectValue placeholder="Prioritaet waehlen" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="low">Niedrig</SelectItem>
                <SelectItem value="medium">Mittel</SelectItem>
                <SelectItem value="high">Hoch</SelectItem>
                <SelectItem value="urgent">Dringend</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Faellig am */}
          <div className="space-y-2">
            <Label htmlFor="task-due-date">Faellig am</Label>
            <Input
              id="task-due-date"
              type="date"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
            />
          </div>

          {/* Zuweisen an (User Search) */}
          <div className="space-y-2">
            <Label>Zuweisen an</Label>
            {assigneeId ? (
              <div className="flex items-center gap-2">
                <div className="flex-1 rounded-md border px-3 py-2 text-sm">
                  {assigneeName}
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleClearAssignee}
                  className="h-8 text-xs"
                >
                  Entfernen
                </Button>
              </div>
            ) : (
              <Popover open={userPopoverOpen} onOpenChange={setUserPopoverOpen}>
                <PopoverTrigger asChild>
                  <Input
                    placeholder="Benutzer suchen..."
                    value={userQuery}
                    onChange={(e) => {
                      setUserQuery(e.target.value);
                      if (e.target.value.length >= 2) {
                        setUserPopoverOpen(true);
                      }
                    }}
                    onFocus={() => {
                      if (userQuery.length >= 2) {
                        setUserPopoverOpen(true);
                      }
                    }}
                  />
                </PopoverTrigger>
                <PopoverContent
                  className="w-[--radix-popover-trigger-width] p-0"
                  align="start"
                  onOpenAutoFocus={(e) => e.preventDefault()}
                >
                  {usersLoading ? (
                    <div className="flex items-center justify-center p-3">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span className="ml-2 text-sm text-muted-foreground">Suche...</span>
                    </div>
                  ) : users.length === 0 ? (
                    <div className="p-3 text-sm text-muted-foreground text-center">
                      Keine Benutzer gefunden
                    </div>
                  ) : (
                    <div className="max-h-48 overflow-auto">
                      {users.map((u) => (
                        <button
                          key={u.id}
                          type="button"
                          className="w-full text-left px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground transition-colors"
                          onClick={() => handleUserSelect(u.id, u.name)}
                        >
                          <div className="font-medium">{u.name}</div>
                          <div className="text-xs text-muted-foreground">{u.email}</div>
                        </button>
                      ))}
                    </div>
                  )}
                </PopoverContent>
              </Popover>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Abbrechen
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!title.trim() || createMutation.isPending}
          >
            {createMutation.isPending && (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            )}
            Erstellen
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
