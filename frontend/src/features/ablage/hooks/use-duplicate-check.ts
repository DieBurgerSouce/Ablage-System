/**
 * Hook fuer Pre-Upload Duplikat-Check.
 *
 * Prueft vor dem Upload, ob ein identisches oder aehnliches Dokument
 * bereits im System existiert.
 */

import { useMutation } from '@tanstack/react-query';
import { checkDuplicatePreUpload, type DuplicateCheckResult } from '../api/ablage-api';
import { toast } from 'sonner';

export function useDuplicateCheck() {
  const mutation = useMutation({
    mutationFn: ({ fileHash, filename }: { fileHash: string; filename: string }) =>
      checkDuplicatePreUpload(fileHash, filename),
    onError: (error: Error) => {
      toast.error('Duplikat-Check fehlgeschlagen', {
        description: error.message || 'Der Check konnte nicht durchgefuehrt werden.',
      });
    },
  });

  return {
    check: mutation.mutateAsync,
    isChecking: mutation.isPending,
    result: mutation.data as DuplicateCheckResult | undefined,
    reset: mutation.reset,
  };
}
