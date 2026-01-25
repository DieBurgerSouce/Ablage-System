/**
 * TeamInvitationList Component
 *
 * Zeigt ausstehende Einladungen und ermoeglicht das Senden neuer Einladungen.
 */

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
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
import { Skeleton } from '@/components/ui/skeleton';
import {
  Mail,
  Clock,
  CheckCircle,
  XCircle,
  RotateCcw,
  Trash2,
  Plus,
  Loader2,
  UserPlus,
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';
import { TeamInvitation, InvitationStatus, TeamMemberRole } from '../api/teams-api';
import { useTeamInvitations, useSendInvitation, useRevokeInvitation } from '../hooks/use-teams';

interface TeamInvitationListProps {
  teamId: string;
  isTeamAdmin?: boolean;
}

const invitationSchema = z.object({
  email: z.string().email('Bitte geben Sie eine gueltige E-Mail-Adresse ein'),
  role: z.enum(['member', 'lead', 'admin', 'deputy', 'observer']),
  message: z.string().max(500, 'Nachricht darf maximal 500 Zeichen haben').optional(),
});

type InvitationFormValues = z.infer<typeof invitationSchema>;

const statusConfig: Record<InvitationStatus, { label: string; icon: React.ElementType; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  pending: { label: 'Ausstehend', icon: Clock, variant: 'secondary' },
  accepted: { label: 'Angenommen', icon: CheckCircle, variant: 'default' },
  declined: { label: 'Abgelehnt', icon: XCircle, variant: 'destructive' },
  expired: { label: 'Abgelaufen', icon: RotateCcw, variant: 'outline' },
  revoked: { label: 'Widerrufen', icon: Trash2, variant: 'outline' },
};

const roleOptions: { value: TeamMemberRole; label: string }[] = [
  { value: 'member', label: 'Mitglied' },
  { value: 'observer', label: 'Beobachter' },
  { value: 'deputy', label: 'Stellvertretung' },
  { value: 'lead', label: 'Leitung' },
  { value: 'admin', label: 'Admin' },
];

export function TeamInvitationList({ teamId, isTeamAdmin = false }: TeamInvitationListProps) {
  const { data: invitations, isLoading } = useTeamInvitations(teamId);
  const sendInvitation = useSendInvitation(teamId);
  const revokeInvitation = useRevokeInvitation(teamId);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [invitationToRevoke, setInvitationToRevoke] = useState<TeamInvitation | null>(null);

  const form = useForm<InvitationFormValues>({
    resolver: zodResolver(invitationSchema),
    defaultValues: {
      email: '',
      role: 'member',
      message: '',
    },
  });

  const onSubmit = async (values: InvitationFormValues) => {
    try {
      await sendInvitation.mutateAsync(values);
      form.reset();
      setDialogOpen(false);
    } catch {
      // Error handling is done in the mutation
    }
  };

  const handleRevoke = () => {
    if (invitationToRevoke) {
      revokeInvitation.mutate(invitationToRevoke.id);
      setInvitationToRevoke(null);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2].map((i) => (
          <div key={i} className="flex items-center gap-3 p-3">
            <Skeleton className="h-10 w-10 rounded-full" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-3 w-32" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  const pendingInvitations = invitations?.filter((i) => i.status === 'pending') ?? [];
  const otherInvitations = invitations?.filter((i) => i.status !== 'pending') ?? [];

  return (
    <div className="space-y-4">
      {/* Send Invitation Button */}
      {isTeamAdmin && (
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button className="w-full">
              <Plus className="h-4 w-4 mr-2" />
              Einladung senden
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Neue Einladung senden</DialogTitle>
              <DialogDescription>
                Laden Sie jemanden per E-Mail zum Team ein.
              </DialogDescription>
            </DialogHeader>

            <Form {...form}>
              <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
                <FormField
                  control={form.control}
                  name="email"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>E-Mail-Adresse</FormLabel>
                      <FormControl>
                        <Input placeholder="beispiel@firma.de" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="role"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Rolle</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Waehlen Sie eine Rolle" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {roleOptions.map((option) => (
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
                  name="message"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Nachricht (optional)</FormLabel>
                      <FormControl>
                        <Textarea
                          placeholder="Persoenliche Nachricht zur Einladung..."
                          className="resize-none"
                          rows={3}
                          {...field}
                        />
                      </FormControl>
                      <FormDescription>Max. 500 Zeichen</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <DialogFooter>
                  <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>
                    Abbrechen
                  </Button>
                  <Button type="submit" disabled={sendInvitation.isPending}>
                    {sendInvitation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    Einladung senden
                  </Button>
                </DialogFooter>
              </form>
            </Form>
          </DialogContent>
        </Dialog>
      )}

      {/* Pending Invitations */}
      {pendingInvitations.length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-muted-foreground mb-2">
            Ausstehende Einladungen ({pendingInvitations.length})
          </h4>
          <div className="space-y-2">
            {pendingInvitations.map((invitation) => (
              <InvitationCard
                key={invitation.id}
                invitation={invitation}
                canRevoke={isTeamAdmin}
                onRevoke={() => setInvitationToRevoke(invitation)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Other Invitations */}
      {otherInvitations.length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-muted-foreground mb-2">
            Fruhere Einladungen ({otherInvitations.length})
          </h4>
          <div className="space-y-2">
            {otherInvitations.slice(0, 5).map((invitation) => (
              <InvitationCard
                key={invitation.id}
                invitation={invitation}
                canRevoke={false}
              />
            ))}
          </div>
        </div>
      )}

      {/* Empty State */}
      {(!invitations || invitations.length === 0) && (
        <div className="text-center py-8 text-muted-foreground">
          <UserPlus className="h-12 w-12 mx-auto mb-2 opacity-50" />
          <p>Keine Einladungen</p>
        </div>
      )}

      {/* Revoke Confirmation */}
      <AlertDialog open={!!invitationToRevoke} onOpenChange={() => setInvitationToRevoke(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Einladung widerrufen?</AlertDialogTitle>
            <AlertDialogDescription>
              Moechten Sie die Einladung an <strong>{invitationToRevoke?.email}</strong> wirklich
              widerrufen? Der Link wird dadurch ungueltig.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction onClick={handleRevoke} className="bg-destructive text-destructive-foreground">
              Widerrufen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

interface InvitationCardProps {
  invitation: TeamInvitation;
  canRevoke: boolean;
  onRevoke?: () => void;
}

function InvitationCard({ invitation, canRevoke, onRevoke }: InvitationCardProps) {
  const config = statusConfig[invitation.status];
  const StatusIcon = config.icon;

  return (
    <div className="flex items-center justify-between p-3 rounded-lg border bg-card">
      <div className="flex items-center gap-3">
        <Avatar>
          <AvatarFallback className="bg-muted">
            <Mail className="h-4 w-4" />
          </AvatarFallback>
        </Avatar>
        <div>
          <div className="font-medium">{invitation.email}</div>
          <div className="text-xs text-muted-foreground">
            Eingeladen{' '}
            {formatDistanceToNow(new Date(invitation.created_at), {
              addSuffix: true,
              locale: de,
            })}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <Badge variant={config.variant} className="flex items-center gap-1">
          <StatusIcon className="h-3 w-3" />
          {config.label}
        </Badge>

        {canRevoke && invitation.status === 'pending' && onRevoke && (
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onRevoke}>
            <Trash2 className="h-4 w-4 text-destructive" />
          </Button>
        )}
      </div>
    </div>
  );
}
