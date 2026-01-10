/**
 * TagsEditDialog - Dialog zum Bearbeiten von Tags für mehrere Dokumente
 *
 * Features:
 * - Drei Modi: Hinzufügen, Entfernen, Ersetzen
 * - Tag-Eingabe mit Autocomplete (falls vorhanden)
 * - WCAG 2.1 AA konform
 * - Loading-States während der Operation
 */

import { useState, useCallback } from 'react';
import { Tags, Plus, Minus, Replace, Loader2, X } from 'lucide-react';
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
import { Badge } from '@/components/ui/badge';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';
import { useBulkSetTags } from '../hooks/use-ablage-queries';

// ==================== Types ====================

type TagMode = 'add' | 'remove' | 'set';

interface TagsEditDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedIds: string[];
  onSuccess?: () => void;
}

const MODE_CONFIG: Record<TagMode, { label: string; icon: React.ElementType; description: string }> = {
  add: {
    label: 'Hinzufügen',
    icon: Plus,
    description: 'Tags werden zu den bestehenden Tags hinzugefügt',
  },
  remove: {
    label: 'Entfernen',
    icon: Minus,
    description: 'Tags werden von den Dokumenten entfernt',
  },
  set: {
    label: 'Ersetzen',
    icon: Replace,
    description: 'Alle bestehenden Tags werden durch die neuen ersetzt',
  },
};

// ==================== Main Component ====================

export function TagsEditDialog({
  open,
  onOpenChange,
  selectedIds,
  onSuccess,
}: TagsEditDialogProps) {
  const [mode, setMode] = useState<TagMode>('add');
  const [tags, setTags] = useState<string[]>([]);
  const [inputValue, setInputValue] = useState('');
  const bulkSetTags = useBulkSetTags();

  // Handle adding a tag
  const handleAddTag = useCallback(() => {
    const trimmed = inputValue.trim().toLowerCase();
    if (trimmed && !tags.includes(trimmed)) {
      setTags((prev) => [...prev, trimmed]);
      setInputValue('');
    }
  }, [inputValue, tags]);

  // Handle removing a tag
  const handleRemoveTag = useCallback((tagToRemove: string) => {
    setTags((prev) => prev.filter((t) => t !== tagToRemove));
  }, []);

  // Handle key press in input
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleAddTag();
      } else if (e.key === 'Backspace' && !inputValue && tags.length > 0) {
        // Remove last tag on backspace if input is empty
        setTags((prev) => prev.slice(0, -1));
      }
    },
    [handleAddTag, inputValue, tags.length]
  );

  // Handle submit
  const handleSubmit = async () => {
    if (tags.length === 0 || selectedIds.length === 0) return;

    try {
      await bulkSetTags.mutateAsync({
        documentIds: selectedIds,
        tags,
        mode,
      });
      onOpenChange(false);
      resetForm();
      onSuccess?.();
    } catch {
      // Error handling is done by the mutation hook via toast
    }
  };

  const resetForm = () => {
    setMode('add');
    setTags([]);
    setInputValue('');
  };

  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen) {
      resetForm();
    }
    onOpenChange(isOpen);
  };

  const currentModeConfig = MODE_CONFIG[mode];

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md" aria-describedby="tags-dialog-description">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Tags className="h-5 w-5" aria-hidden="true" />
            Tags bearbeiten
          </DialogTitle>
          <DialogDescription id="tags-dialog-description">
            Bearbeiten Sie die Tags für{' '}
            <span className="font-semibold">{selectedIds.length} Dokumente</span>.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Mode Selection */}
          <div className="space-y-2">
            <Label>Modus</Label>
            <ToggleGroup
              type="single"
              value={mode}
              onValueChange={(v) => v && setMode(v as TagMode)}
              className="justify-start"
            >
              {(Object.entries(MODE_CONFIG) as [TagMode, typeof MODE_CONFIG.add][]).map(
                ([key, config]) => {
                  const Icon = config.icon;
                  return (
                    <ToggleGroupItem
                      key={key}
                      value={key}
                      aria-label={config.label}
                      className="data-[state=on]:bg-primary data-[state=on]:text-primary-foreground"
                    >
                      <Icon className="h-4 w-4 mr-2" aria-hidden="true" />
                      {config.label}
                    </ToggleGroupItem>
                  );
                }
              )}
            </ToggleGroup>
            <p className="text-sm text-muted-foreground">{currentModeConfig.description}</p>
          </div>

          {/* Tag Input */}
          <div className="space-y-2">
            <Label htmlFor="tag-input">Tags</Label>
            <div
              className={cn(
                'flex flex-wrap gap-2 p-2 border rounded-md min-h-[80px]',
                'focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2'
              )}
            >
              {tags.map((tag) => (
                <Badge
                  key={tag}
                  variant="secondary"
                  className="h-7 gap-1 pr-1"
                >
                  {tag}
                  <button
                    type="button"
                    onClick={() => handleRemoveTag(tag)}
                    className="ml-1 rounded-full p-0.5 hover:bg-muted-foreground/20"
                    aria-label={`Tag "${tag}" entfernen`}
                  >
                    <X className="h-3 w-3" aria-hidden="true" />
                  </button>
                </Badge>
              ))}
              <Input
                id="tag-input"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                onBlur={handleAddTag}
                placeholder={tags.length === 0 ? 'Tag eingeben und Enter drücken...' : ''}
                className="flex-1 min-w-[120px] border-0 shadow-none focus-visible:ring-0 h-7 p-0"
                aria-describedby="tag-input-help"
              />
            </div>
            <p id="tag-input-help" className="text-xs text-muted-foreground">
              Drücken Sie Enter oder Tab zum Hinzufügen eines Tags
            </p>
          </div>
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            variant="outline"
            onClick={() => handleOpenChange(false)}
            disabled={bulkSetTags.isPending}
          >
            Abbrechen
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={tags.length === 0 || bulkSetTags.isPending}
            aria-label={`Tags für ${selectedIds.length} Dokumente ${currentModeConfig.label.toLowerCase()}`}
          >
            {bulkSetTags.isPending ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" aria-hidden="true" />
                Wird verarbeitet...
              </>
            ) : (
              <>
                <currentModeConfig.icon className="h-4 w-4 mr-2" aria-hidden="true" />
                {currentModeConfig.label}
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default TagsEditDialog;
