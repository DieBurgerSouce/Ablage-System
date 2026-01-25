/**
 * TeamMemberList Component
 *
 * Zeigt die Mitglieder eines Teams mit Rollen-Management an.
 */

import { useState } from 'react';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
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
import { MoreHorizontal, UserMinus, Shield, UserCog, Crown, Eye, Users } from 'lucide-react';
import { TeamMember, TeamMemberRole } from '../api/teams-api';
import { useTeamMembers, useUpdateMemberRole, useRemoveMember } from '../hooks/use-teams';

interface TeamMemberListProps {
  teamId: string;
  currentUserId?: string;
  isTeamAdmin?: boolean;
}

const roleConfig: Record<TeamMemberRole, { label: string; icon: React.ElementType; color: string }> = {
  admin: { label: 'Admin', icon: Shield, color: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200' },
  lead: { label: 'Leitung', icon: Crown, color: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200' },
  deputy: { label: 'Stellvertretung', icon: UserCog, color: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200' },
  member: { label: 'Mitglied', icon: Users, color: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200' },
  observer: { label: 'Beobachter', icon: Eye, color: 'bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-200' },
};

export function TeamMemberList({ teamId, currentUserId, isTeamAdmin = false }: TeamMemberListProps) {
  const { data: members, isLoading } = useTeamMembers(teamId);
  const updateRole = useUpdateMemberRole(teamId);
  const removeMember = useRemoveMember(teamId);

  const [memberToRemove, setMemberToRemove] = useState<TeamMember | null>(null);

  const handleRoleChange = (userId: string, role: TeamMemberRole) => {
    updateRole.mutate({ userId, data: { role } });
  };

  const handleRemove = () => {
    if (memberToRemove) {
      removeMember.mutate(memberToRemove.user_id);
      setMemberToRemove(null);
    }
  };

  const getInitials = (member: TeamMember) => {
    if (member.user?.full_name) {
      const parts = member.user.full_name.split(' ');
      if (parts.length >= 2) {
        return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
      }
      return member.user.full_name.substring(0, 2).toUpperCase();
    }
    if (member.user?.username) {
      return member.user.username.substring(0, 2).toUpperCase();
    }
    return 'U';
  };

  const getDisplayName = (member: TeamMember) => {
    return member.user?.full_name || member.user?.username || 'Unbekannt';
  };

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex items-center gap-3 p-3">
            <Skeleton className="h-10 w-10 rounded-full" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-24" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (!members || members.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Users className="h-12 w-12 mx-auto mb-2 opacity-50" />
        <p>Keine Mitglieder</p>
      </div>
    );
  }

  // Sort: admins first, then leads, then by name
  const sortedMembers = [...members].sort((a, b) => {
    const roleOrder: Record<TeamMemberRole, number> = {
      admin: 0,
      lead: 1,
      deputy: 2,
      member: 3,
      observer: 4,
    };
    const orderDiff = roleOrder[a.role] - roleOrder[b.role];
    if (orderDiff !== 0) return orderDiff;
    return getDisplayName(a).localeCompare(getDisplayName(b));
  });

  return (
    <>
      <div className="space-y-1">
        {sortedMembers.map((member) => {
          const config = roleConfig[member.role];
          const RoleIcon = config.icon;
          const isCurrentUser = member.user_id === currentUserId;
          const canManage = isTeamAdmin && !isCurrentUser;

          return (
            <div
              key={member.id}
              className="flex items-center justify-between p-3 rounded-lg hover:bg-muted/50 transition-colors"
            >
              <div className="flex items-center gap-3">
                <Avatar>
                  <AvatarFallback className="bg-primary/10 text-primary">
                    {getInitials(member)}
                  </AvatarFallback>
                </Avatar>
                <div>
                  <div className="font-medium flex items-center gap-2">
                    {getDisplayName(member)}
                    {isCurrentUser && (
                      <Badge variant="outline" className="text-xs">
                        Du
                      </Badge>
                    )}
                  </div>
                  <div className="text-sm text-muted-foreground">
                    {member.user?.email}
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <Badge className={config.color}>
                  <RoleIcon className="h-3 w-3 mr-1" />
                  {config.label}
                </Badge>

                {canManage && (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon" className="h-8 w-8">
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem
                        onClick={() => handleRoleChange(member.user_id, 'admin')}
                        disabled={member.role === 'admin'}
                      >
                        <Shield className="h-4 w-4 mr-2" />
                        Zum Admin machen
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        onClick={() => handleRoleChange(member.user_id, 'lead')}
                        disabled={member.role === 'lead'}
                      >
                        <Crown className="h-4 w-4 mr-2" />
                        Zur Leitung machen
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        onClick={() => handleRoleChange(member.user_id, 'deputy')}
                        disabled={member.role === 'deputy'}
                      >
                        <UserCog className="h-4 w-4 mr-2" />
                        Zur Stellvertretung machen
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        onClick={() => handleRoleChange(member.user_id, 'member')}
                        disabled={member.role === 'member'}
                      >
                        <Users className="h-4 w-4 mr-2" />
                        Zum Mitglied machen
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        onClick={() => handleRoleChange(member.user_id, 'observer')}
                        disabled={member.role === 'observer'}
                      >
                        <Eye className="h-4 w-4 mr-2" />
                        Zum Beobachter machen
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        onClick={() => setMemberToRemove(member)}
                        className="text-destructive"
                      >
                        <UserMinus className="h-4 w-4 mr-2" />
                        Entfernen
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Remove Member Confirmation */}
      <AlertDialog open={!!memberToRemove} onOpenChange={() => setMemberToRemove(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Mitglied entfernen?</AlertDialogTitle>
            <AlertDialogDescription>
              Moechten Sie{' '}
              <strong>
                {memberToRemove?.user?.full_name || memberToRemove?.user?.username}
              </strong>{' '}
              wirklich aus dem Team entfernen? Diese Aktion kann nicht rueckgaengig gemacht werden.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction onClick={handleRemove} className="bg-destructive text-destructive-foreground">
              Entfernen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
