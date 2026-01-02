/**
 * Cash Register Form
 *
 * Formular zum Erstellen/Bearbeiten einer Kasse.
 */

import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { Loader2 } from 'lucide-react';
import { useCreateRegister, useUpdateRegister } from '../hooks/use-cash-queries';
import type { CashRegister, CashRegisterCreate, CashRegisterUpdate } from '@/types/models/cash';

// Validierungs-Schema
const registerSchema = z.object({
  name: z.string().min(1, 'Name ist erforderlich').max(100, 'Name zu lang'),
  description: z.string().max(500, 'Beschreibung zu lang').optional(),
  opening_balance: z.number().min(0, 'Saldo muss positiv sein').optional(),
  is_active: z.boolean().default(true),
});

type RegisterFormData = z.infer<typeof registerSchema>;

interface CashRegisterFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  register?: CashRegister | null;
  onSuccess?: (register: CashRegister) => void;
}

export function CashRegisterForm({
  open,
  onOpenChange,
  register,
  onSuccess,
}: CashRegisterFormProps) {
  const isEditing = !!register;
  const createMutation = useCreateRegister();
  const updateMutation = useUpdateRegister();

  const form = useForm<RegisterFormData>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      name: register?.name ?? '',
      description: register?.description ?? '',
      opening_balance: isEditing ? undefined : 0,
      is_active: register?.is_active ?? true,
    },
  });

  // Formular zurücksetzen wenn Register wechselt
  React.useEffect(() => {
    if (open) {
      form.reset({
        name: register?.name ?? '',
        description: register?.description ?? '',
        opening_balance: isEditing ? undefined : 0,
        is_active: register?.is_active ?? true,
      });
    }
  }, [open, register, isEditing, form]);

  const onSubmit = async (data: RegisterFormData) => {
    try {
      if (isEditing && register) {
        const updateData: CashRegisterUpdate = {
          name: data.name,
          description: data.description,
          is_active: data.is_active,
        };
        const result = await updateMutation.mutateAsync({
          id: register.id,
          data: updateData,
        });
        onSuccess?.(result);
      } else {
        const createData: CashRegisterCreate = {
          name: data.name,
          description: data.description,
          opening_balance: data.opening_balance ?? 0,
        };
        const result = await createMutation.mutateAsync(createData);
        onSuccess?.(result);
      }
      onOpenChange(false);
    } catch (error) {
      // Fehler werden vom Mutation-Hook behandelt
    }
  };

  const isSubmitting = createMutation.isPending || updateMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>
            {isEditing ? 'Kasse bearbeiten' : 'Neue Kasse erstellen'}
          </DialogTitle>
          <DialogDescription>
            {isEditing
              ? 'Ändern Sie die Kassendetails.'
              : 'Erstellen Sie eine neue Barkasse für Ihr Unternehmen.'}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name *</FormLabel>
                  <FormControl>
                    <Input placeholder="z.B. Hauptkasse, Handkasse" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Beschreibung</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="Optionale Beschreibung der Kasse..."
                      className="resize-none"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {!isEditing && (
              <FormField
                control={form.control}
                name="opening_balance"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Anfangssaldo (EUR)</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        step="0.01"
                        min="0"
                        placeholder="0.00"
                        {...field}
                        onChange={(e) => field.onChange(parseFloat(e.target.value) || 0)}
                      />
                    </FormControl>
                    <FormDescription>
                      Der Anfangsbestand der Kasse
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}

            {isEditing && (
              <FormField
                control={form.control}
                name="is_active"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
                    <div className="space-y-0.5">
                      <FormLabel>Aktiv</FormLabel>
                      <FormDescription>
                        Inaktive Kassen können keine neuen Buchungen erhalten
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch
                        checked={field.value}
                        onCheckedChange={field.onChange}
                      />
                    </FormControl>
                  </FormItem>
                )}
              />
            )}

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={isSubmitting}
              >
                Abbrechen
              </Button>
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />}
                {isEditing ? 'Speichern' : 'Erstellen'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}

export default CashRegisterForm;
