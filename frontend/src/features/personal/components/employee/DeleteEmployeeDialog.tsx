/**
 * DeleteEmployeeDialog - Mitarbeiter löschen Bestätigung
 *
 * Warnt vor dem Löschen und bestätigt die Aktion.
 */

import { Loader2 } from 'lucide-react';
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
import { useToast } from '@/components/ui/use-toast';
import { useDeleteEmployee } from '../../hooks/use-personal-queries';
import type { Employee } from '../../types';

interface DeleteEmployeeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  employee: Employee | null;
  onSuccess?: () => void;
}

export function DeleteEmployeeDialog({
  open,
  onOpenChange,
  employee,
  onSuccess,
}: DeleteEmployeeDialogProps) {
  const { toast } = useToast();
  const deleteMutation = useDeleteEmployee();

  const handleDelete = async () => {
    if (!employee) return;

    try {
      await deleteMutation.mutateAsync(employee.id);
      toast({
        title: 'Mitarbeiter gelöscht',
        description: `${employee.full_name} wurde erfolgreich gelöscht.`,
      });
      onOpenChange(false);
      onSuccess?.();
    } catch (error) {
      toast({
        title: 'Fehler',
        description: error instanceof Error ? error.message : 'Löschen fehlgeschlagen',
        variant: 'destructive',
      });
    }
  };

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Mitarbeiter löschen</AlertDialogTitle>
          <AlertDialogDescription>
            Möchten Sie den Mitarbeiter{' '}
            <span className="font-semibold">{employee?.full_name}</span>{' '}
            (Personalnummer: {employee?.employee_number}) wirklich löschen?
            <br />
            <br />
            Diese Aktion kann nicht rückgängig gemacht werden. Alle zugeordneten
            Dokumente bleiben erhalten, der Mitarbeiter wird jedoch als gelöscht markiert.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={deleteMutation.isPending}>
            Abbrechen
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={handleDelete}
            disabled={deleteMutation.isPending}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {deleteMutation.isPending && (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            )}
            Löschen
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
