/**
 * Toast Hook Re-export
 *
 * Re-exportiert useToast von components/ui für Rückwärtskompatibilität.
 * Neue Komponenten sollten direkt `import { toast } from 'sonner'` verwenden.
 */

export { useToast, toast } from '@/components/ui/use-toast';
export type { Toast, ToasterToast, ToastVariant } from '@/components/ui/use-toast';
