/**
 * MoveFolderDialog - Dialog zum Verschieben von Dokumenten in andere Kategorien
 *
 * Features:
 * - Kategorieauswahl mit Icons
 * - Unterstuetzung fuer Kunden- und Lieferanten-Kategorien
 * - WCAG 2.1 AA konform
 * - Loading-States waehrend der Operation
 */

import { useState } from 'react';
import { FolderInput, Loader2 } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import { useBulkMoveCategory } from '../hooks/use-ablage-queries';
import {
  CUSTOMER_CATEGORIES,
  SUPPLIER_CATEGORIES,
  type DocumentCategoryInfo,
} from '../types';
import * as LucideIcons from 'lucide-react';

// ==================== Types ====================

interface MoveFolderDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedIds: string[];
  currentCategory: string;
  entityType: 'customer' | 'supplier';
  onSuccess?: () => void;
}

// ==================== Helper ====================

function getCategoryIcon(iconName: string): React.ElementType {
  const icons = LucideIcons as Record<string, React.ElementType>;
  return icons[iconName] || LucideIcons.FileText;
}

// ==================== Main Component ====================

export function MoveFolderDialog({
  open,
  onOpenChange,
  selectedIds,
  currentCategory,
  entityType,
  onSuccess,
}: MoveFolderDialogProps) {
  const [targetCategory, setTargetCategory] = useState<string>('');
  const bulkMove = useBulkMoveCategory();

  // Get available categories based on entity type
  const categories: DocumentCategoryInfo[] =
    entityType === 'supplier' ? SUPPLIER_CATEGORIES : CUSTOMER_CATEGORIES;

  // Filter out current category and "open" status categories
  const availableCategories = categories.filter(
    (cat) => cat.id !== currentCategory && !cat.isOpenStatus
  );

  const handleMove = async () => {
    if (!targetCategory || selectedIds.length === 0) return;

    try {
      await bulkMove.mutateAsync({
        documentIds: selectedIds,
        targetCategory,
      });
      onOpenChange(false);
      setTargetCategory('');
      onSuccess?.();
    } catch {
      // Error handling is done by the mutation hook via toast
    }
  };

  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen) {
      setTargetCategory('');
    }
    onOpenChange(isOpen);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md" aria-describedby="move-dialog-description">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FolderInput className="h-5 w-5" aria-hidden="true" />
            In Ordner verschieben
          </DialogTitle>
          <DialogDescription id="move-dialog-description">
            Waehlen Sie die Zielkategorie fuer{' '}
            <span className="font-semibold">{selectedIds.length} Dokumente</span>.
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="max-h-[400px] pr-4">
          <RadioGroup
            value={targetCategory}
            onValueChange={setTargetCategory}
            className="gap-2"
            aria-label="Zielkategorie auswaehlen"
          >
            {availableCategories.map((category) => {
              const Icon = getCategoryIcon(category.icon);
              return (
                <div key={category.id}>
                  <RadioGroupItem
                    value={category.id}
                    id={`category-${category.id}`}
                    className="peer sr-only"
                    aria-describedby={`category-${category.id}-label`}
                  />
                  <Label
                    htmlFor={`category-${category.id}`}
                    id={`category-${category.id}-label`}
                    className={cn(
                      'flex items-center gap-3 rounded-lg border-2 border-muted bg-popover p-4 cursor-pointer',
                      'hover:bg-accent hover:text-accent-foreground',
                      'peer-data-[state=checked]:border-primary peer-data-[state=checked]:bg-primary/5',
                      'transition-all duration-150'
                    )}
                  >
                    <Icon className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
                    <div className="flex-1">
                      <span className="font-medium">{category.label}</span>
                      {category.shortCode && (
                        <span className="ml-2 text-xs text-muted-foreground">
                          ({category.shortCode})
                        </span>
                      )}
                    </div>
                  </Label>
                </div>
              );
            })}
          </RadioGroup>
        </ScrollArea>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            variant="outline"
            onClick={() => handleOpenChange(false)}
            disabled={bulkMove.isPending}
          >
            Abbrechen
          </Button>
          <Button
            onClick={handleMove}
            disabled={!targetCategory || bulkMove.isPending}
            aria-label={`${selectedIds.length} Dokumente in ${
              categories.find((c) => c.id === targetCategory)?.label || 'ausgewaehlte Kategorie'
            } verschieben`}
          >
            {bulkMove.isPending ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" aria-hidden="true" />
                Wird verschoben...
              </>
            ) : (
              <>
                <FolderInput className="h-4 w-4 mr-2" aria-hidden="true" />
                Verschieben
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default MoveFolderDialog;
