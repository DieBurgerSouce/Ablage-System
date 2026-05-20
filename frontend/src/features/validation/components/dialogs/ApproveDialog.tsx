/**
 * ApproveDialog
 *
 * Dialog zur Verifizierung eines Training-Samples.
 */

import { useState } from 'react';
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
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Check } from 'lucide-react';

interface ApproveDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (notes?: string) => Promise<void>;
  isLoading?: boolean;
  documentName: string;
}

export function ApproveDialog({
  open,
  onOpenChange,
  onConfirm,
  isLoading,
  documentName,
}: ApproveDialogProps) {
  const [notes, setNotes] = useState('');

  const handleConfirm = async () => {
    await onConfirm(notes || undefined);
    setNotes('');
  };

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <Check className="w-5 h-5 text-green-600" />
            Sample verifizieren
          </AlertDialogTitle>
          <AlertDialogDescription>
            Möchten Sie das Sample &quot;{documentName}&quot; als verifiziert markieren?
            Dies bestätigt, dass die annotierten Daten korrekt sind.
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="py-4 space-y-2">
          <Label htmlFor="approve-notes">Optionale Notizen</Label>
          <Textarea
            id="approve-notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Anmerkungen zur Verifizierung..."
            rows={3}
          />
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel disabled={isLoading}>Abbrechen</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleConfirm}
            disabled={isLoading}
            className="bg-green-600 hover:bg-green-700"
          >
            {isLoading ? 'Verifiziere...' : 'Verifizieren'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
