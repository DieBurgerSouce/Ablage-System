/**
 * TeamDetailDialog Component
 *
 * Dialog zur Anzeige der Team-Details mit Tabs für Mitglieder, Aktivitäten, etc.
 */

import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Users,
  FileText,
  Activity,
  Mail,
  Settings,
  UserPlus,
  Building2,
  FolderKanban,
  Briefcase,
  Users2,
  Globe,
  Eye,
  EyeOff,
} from 'lucide-react';
import type { Team, TeamType, TeamStatus, TeamVisibility } from '../api/teams-api';
import { useTeam } from '../hooks/use-teams';
import { useAuth } from '@/lib/auth/AuthContext';
import { TeamMemberList } from './TeamMemberList';
import { TeamActivityFeed } from './TeamActivityFeed';
import { TeamInvitationList } from './TeamInvitationList';
import { TeamDocumentList } from './TeamDocumentList';
import { AddMemberDialog } from './AddMemberDialog';

interface TeamDetailDialogProps {
  teamId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onEdit: (team: Team) => void;
}

const teamTypeConfig: Record<TeamType, { label: string; icon: React.ElementType }> = {
  department: { label: 'Abteilung', icon: Building2 },
  project: { label: 'Projekt', icon: FolderKanban },
  working_group: { label: 'Arbeitsgruppe', icon: Users2 },
  committee: { label: 'Gremium', icon: Briefcase },
  virtual: { label: 'Virtuell', icon: Globe },
};

const statusConfig: Record<TeamStatus, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  active: { label: 'Aktiv', variant: 'default' },
  inactive: { label: 'Inaktiv', variant: 'secondary' },
  archived: { label: 'Archiviert', variant: 'outline' },
  pending: { label: 'Ausstehend', variant: 'secondary' },
};

const visibilityConfig: Record<TeamVisibility, { label: string; icon: React.ElementType }> = {
  public: { label: 'Öffentlich', icon: Eye },
  private: { label: 'Privat', icon: EyeOff },
  company: { label: 'Firma', icon: Building2 },
};

export function TeamDetailDialog({ teamId, open, onOpenChange, onEdit }: TeamDetailDialogProps) {
  const { user } = useAuth();
  const { data: team, isLoading } = useTeam(teamId ?? '');
  const [addMemberOpen, setAddMemberOpen] = useState(false);

  // Check if current user is team admin (simplified - would need proper check against members)
  const isTeamAdmin = user?.role === 'admin'; // Simplified for now

  if (!teamId) return null;

  const TypeIcon = team ? teamTypeConfig[team.team_type].icon : Building2;
  const VisibilityIcon = team ? visibilityConfig[team.visibility].icon : Eye;

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-4xl max-h-[90vh] flex flex-col">
          <DialogHeader>
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-primary/10">
                  <TypeIcon className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <DialogTitle className="text-xl">
                    {isLoading ? 'Laden...' : team?.name || 'Team'}
                  </DialogTitle>
                  <DialogDescription>
                    {team && teamTypeConfig[team.team_type].label}
                  </DialogDescription>
                </div>
              </div>
              {team && (
                <div className="flex items-center gap-2">
                  <Badge variant={statusConfig[team.status].variant}>
                    {statusConfig[team.status].label}
                  </Badge>
                  <Badge variant="outline" className="flex items-center gap-1">
                    <VisibilityIcon className="h-3 w-3" />
                    {visibilityConfig[team.visibility].label}
                  </Badge>
                </div>
              )}
            </div>
          </DialogHeader>

          {team?.description && (
            <p className="text-sm text-muted-foreground px-1">{team.description}</p>
          )}

          <Tabs defaultValue="members" className="flex-1 flex flex-col min-h-0">
            <TabsList className="grid w-full grid-cols-4">
              <TabsTrigger value="members" className="flex items-center gap-2">
                <Users className="h-4 w-4" />
                <span className="hidden sm:inline">Mitglieder</span>
              </TabsTrigger>
              <TabsTrigger value="documents" className="flex items-center gap-2">
                <FileText className="h-4 w-4" />
                <span className="hidden sm:inline">Dokumente</span>
              </TabsTrigger>
              <TabsTrigger value="activity" className="flex items-center gap-2">
                <Activity className="h-4 w-4" />
                <span className="hidden sm:inline">Aktivität</span>
              </TabsTrigger>
              <TabsTrigger value="invitations" className="flex items-center gap-2">
                <Mail className="h-4 w-4" />
                <span className="hidden sm:inline">Einladungen</span>
              </TabsTrigger>
            </TabsList>

            <ScrollArea className="flex-1 mt-4">
              <TabsContent value="members" className="m-0 pr-4">
                <div className="flex justify-between items-center mb-4">
                  <h3 className="font-medium">
                    {team?.member_count ?? 0} Mitglieder
                  </h3>
                  {isTeamAdmin && (
                    <Button size="sm" onClick={() => setAddMemberOpen(true)}>
                      <UserPlus className="h-4 w-4 mr-2" />
                      Hinzufügen
                    </Button>
                  )}
                </div>
                <TeamMemberList
                  teamId={teamId}
                  currentUserId={user?.id}
                  isTeamAdmin={isTeamAdmin}
                />
              </TabsContent>

              <TabsContent value="documents" className="m-0 pr-4">
                <div className="flex justify-between items-center mb-4">
                  <h3 className="font-medium">
                    {team?.document_count ?? 0} geteilte Dokumente
                  </h3>
                </div>
                <TeamDocumentList teamId={teamId} isTeamAdmin={isTeamAdmin} />
              </TabsContent>

              <TabsContent value="activity" className="m-0 pr-4">
                <h3 className="font-medium mb-4">Aktivitäts-Feed</h3>
                <TeamActivityFeed teamId={teamId} />
              </TabsContent>

              <TabsContent value="invitations" className="m-0 pr-4">
                <h3 className="font-medium mb-4">Einladungen verwalten</h3>
                <TeamInvitationList teamId={teamId} isTeamAdmin={isTeamAdmin} />
              </TabsContent>
            </ScrollArea>
          </Tabs>

          {/* Footer Actions */}
          <div className="flex justify-end gap-2 pt-4 border-t">
            {isTeamAdmin && team && (
              <Button variant="outline" onClick={() => onEdit(team)}>
                <Settings className="h-4 w-4 mr-2" />
                Einstellungen
              </Button>
            )}
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Schließen
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Add Member Dialog */}
      {teamId && (
        <AddMemberDialog
          teamId={teamId}
          open={addMemberOpen}
          onOpenChange={setAddMemberOpen}
        />
      )}
    </>
  );
}
