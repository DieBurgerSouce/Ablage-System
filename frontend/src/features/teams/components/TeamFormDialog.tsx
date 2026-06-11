/**
 * TeamFormDialog Component
 *
 * Dialog zum Erstellen und Bearbeiten von Teams.
 */

import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '@/components/ui/button';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Loader2 } from 'lucide-react';
import type { Team, TeamType, TeamVisibility } from '../api/teams-api';
import { useCreateTeam, useUpdateTeam } from '../hooks/use-teams';

const teamSchema = z.object({
  name: z.string().min(2, 'Name muss mindestens 2 Zeichen haben').max(100, 'Name darf maximal 100 Zeichen haben'),
  description: z.string().max(500, 'Beschreibung darf maximal 500 Zeichen haben').optional(),
  team_type: z.enum(['department', 'project', 'working_group', 'committee', 'virtual']),
  visibility: z.enum(['public', 'private', 'company']),
});

type TeamFormValues = z.infer<typeof teamSchema>;

interface TeamFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  team?: Team | null;
}

const teamTypeOptions: { value: TeamType; label: string }[] = [
  { value: 'department', label: 'Abteilung' },
  { value: 'project', label: 'Projekt' },
  { value: 'working_group', label: 'Arbeitsgruppe' },
  { value: 'committee', label: 'Gremium' },
  { value: 'virtual', label: 'Virtuelles Team' },
];

const visibilityOptions: { value: TeamVisibility; label: string; description: string }[] = [
  { value: 'public', label: 'Öffentlich', description: 'Sichtbar für alle Benutzer' },
  { value: 'private', label: 'Privat', description: 'Nur für Mitglieder sichtbar' },
  { value: 'company', label: 'Firma', description: 'Sichtbar für alle Firmenmitglieder' },
];

export function TeamFormDialog({ open, onOpenChange, team }: TeamFormDialogProps) {
  const isEditing = !!team;
  const createTeam = useCreateTeam();
  const updateTeam = useUpdateTeam(team?.id ?? '');

  const form = useForm<TeamFormValues>({
    resolver: zodResolver(teamSchema),
    defaultValues: {
      name: '',
      description: '',
      team_type: 'project',
      visibility: 'company',
    },
  });

  // Reset form when dialog opens/closes or team changes
  useEffect(() => {
    if (open) {
      if (team) {
        form.reset({
          name: team.name,
          description: team.description ?? '',
          team_type: team.team_type,
          visibility: team.visibility,
        });
      } else {
        form.reset({
          name: '',
          description: '',
          team_type: 'project',
          visibility: 'company',
        });
      }
    }
  }, [open, team, form]);

  const onSubmit = async (values: TeamFormValues) => {
    try {
      if (isEditing) {
        await updateTeam.mutateAsync(values);
      } else {
        await createTeam.mutateAsync(values);
      }
      onOpenChange(false);
    } catch {
      // Error handling is done in the mutation
    }
  };

  const isLoading = createTeam.isPending || updateTeam.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>{isEditing ? 'Team bearbeiten' : 'Neues Team erstellen'}</DialogTitle>
          <DialogDescription>
            {isEditing
              ? 'Bearbeiten Sie die Einstellungen für dieses Team.'
              : 'Erstellen Sie ein neues Team für die Zusammenarbeit.'}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input placeholder="z.B. Marketing Team" {...field} />
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
                      placeholder="Beschreiben Sie den Zweck des Teams..."
                      className="resize-none"
                      rows={3}
                      {...field}
                    />
                  </FormControl>
                  <FormDescription>Optional - max. 500 Zeichen</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="team_type"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Team-Typ</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Wählen Sie einen Team-Typ" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {teamTypeOptions.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="visibility"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Sichtbarkeit</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Wählen Sie die Sichtbarkeit" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {visibilityOptions.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          <div>
                            <div>{option.label}</div>
                            <div className="text-xs text-muted-foreground">{option.description}</div>
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Abbrechen
              </Button>
              <Button type="submit" disabled={isLoading}>
                {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {isEditing ? 'Speichern' : 'Erstellen'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
