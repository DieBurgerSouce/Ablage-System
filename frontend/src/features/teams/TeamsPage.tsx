/**
 * TeamsPage Component
 *
 * Hauptseite für die Team-Verwaltung mit Übersicht aller Teams.
 */

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
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
import { Users2, Plus, Search, Building2, Users, FileText } from 'lucide-react';
import type { Team, TeamType, TeamStatus } from './api/teams-api';
import { useTeams, useDeleteTeam, useArchiveTeam } from './hooks/use-teams';
import { TeamCard, TeamFormDialog, TeamDetailDialog } from './components';

const teamTypeFilters: { value: TeamType | 'all'; label: string }[] = [
  { value: 'all', label: 'Alle Typen' },
  { value: 'department', label: 'Abteilungen' },
  { value: 'project', label: 'Projekte' },
  { value: 'working_group', label: 'Arbeitsgruppen' },
  { value: 'committee', label: 'Gremien' },
  { value: 'virtual', label: 'Virtuelle Teams' },
];

const statusFilters: { value: TeamStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'Alle Status' },
  { value: 'active', label: 'Aktiv' },
  { value: 'inactive', label: 'Inaktiv' },
  { value: 'archived', label: 'Archiviert' },
  { value: 'pending', label: 'Ausstehend' },
];

export function TeamsPage() {
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<TeamType | 'all'>('all');
  const [statusFilter, setStatusFilter] = useState<TeamStatus | 'all'>('active');

  // Dialog states
  const [formDialogOpen, setFormDialogOpen] = useState(false);
  const [editingTeam, setEditingTeam] = useState<Team | null>(null);
  const [detailTeamId, setDetailTeamId] = useState<string | null>(null);
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [teamToDelete, setTeamToDelete] = useState<Team | null>(null);
  const [teamToArchive, setTeamToArchive] = useState<Team | null>(null);

  // Query and mutations
  const { data, isLoading } = useTeams({
    search: search || undefined,
    team_type: typeFilter === 'all' ? undefined : typeFilter,
    status: statusFilter === 'all' ? undefined : statusFilter,
    page_size: 100,
  });
  const deleteTeam = useDeleteTeam();
  const archiveTeamMutation = useArchiveTeam(teamToArchive?.id ?? '');

  const teams = data?.teams ?? [];

  // Stats
  const totalTeams = teams.length;
  const totalMembers = teams.reduce((sum, t) => sum + (t.member_count ?? 0), 0);
  const totalDocuments = teams.reduce((sum, t) => sum + (t.document_count ?? 0), 0);
  const activeTeams = teams.filter((t) => t.status === 'active').length;

  // Handlers
  const handleView = (team: Team) => {
    setDetailTeamId(team.id);
    setDetailDialogOpen(true);
  };

  const handleEdit = (team: Team) => {
    setEditingTeam(team);
    setFormDialogOpen(true);
    setDetailDialogOpen(false);
  };

  const handleCreate = () => {
    setEditingTeam(null);
    setFormDialogOpen(true);
  };

  const handleFormDialogClose = (open: boolean) => {
    setFormDialogOpen(open);
    if (!open) {
      setEditingTeam(null);
    }
  };

  const handleDelete = () => {
    if (teamToDelete) {
      deleteTeam.mutate(teamToDelete.id);
      setTeamToDelete(null);
    }
  };

  const handleArchive = () => {
    if (teamToArchive) {
      archiveTeamMutation.mutate();
      setTeamToArchive(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Users2 className="h-6 w-6" />
            Team Workspaces
          </h1>
          <p className="text-muted-foreground">
            Verwalten Sie Teams, Mitglieder und geteilte Dokumente.
          </p>
        </div>

        <Button onClick={handleCreate}>
          <Plus className="h-4 w-4 mr-2" />
          Neues Team
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Teams gesamt
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <Users2 className="h-4 w-4 text-muted-foreground" />
              <span className="text-2xl font-bold">{totalTeams}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Aktive Teams
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <Building2 className="h-4 w-4 text-green-500" />
              <span className="text-2xl font-bold">{activeTeams}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Mitglieder gesamt
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <Users className="h-4 w-4 text-blue-500" />
              <span className="text-2xl font-bold">{totalMembers}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Geteilte Dokumente
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-purple-500" />
              <span className="text-2xl font-bold">{totalDocuments}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Teams suchen..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
          />
        </div>

        <Select
          value={typeFilter}
          onValueChange={(value) => setTypeFilter(value as TeamType | 'all')}
        >
          <SelectTrigger className="w-full sm:w-[180px]">
            <SelectValue placeholder="Team-Typ" />
          </SelectTrigger>
          <SelectContent>
            {teamTypeFilters.map((filter) => (
              <SelectItem key={filter.value} value={filter.value}>
                {filter.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={statusFilter}
          onValueChange={(value) => setStatusFilter(value as TeamStatus | 'all')}
        >
          <SelectTrigger className="w-full sm:w-[180px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            {statusFilters.map((filter) => (
              <SelectItem key={filter.value} value={filter.value}>
                {filter.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Teams Grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Card key={i}>
              <CardHeader className="pb-2">
                <Skeleton className="h-5 w-32" />
                <Skeleton className="h-4 w-24" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-4 w-full mb-3" />
                <div className="flex gap-4">
                  <Skeleton className="h-4 w-20" />
                  <Skeleton className="h-4 w-20" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : teams.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Users2 className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium mb-1">Keine Teams gefunden</h3>
            <p className="text-muted-foreground text-center mb-4">
              {search || typeFilter !== 'all' || statusFilter !== 'all'
                ? 'Versuchen Sie andere Filterkriterien.'
                : 'Erstellen Sie Ihr erstes Team, um loszulegen.'}
            </p>
            {!search && typeFilter === 'all' && statusFilter === 'all' && (
              <Button onClick={handleCreate}>
                <Plus className="h-4 w-4 mr-2" />
                Erstes Team erstellen
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {teams.map((team) => (
            <TeamCard
              key={team.id}
              team={team}
              onView={handleView}
              onEdit={handleEdit}
              onArchive={setTeamToArchive}
              onDelete={setTeamToDelete}
            />
          ))}
        </div>
      )}

      {/* Form Dialog */}
      <TeamFormDialog
        open={formDialogOpen}
        onOpenChange={handleFormDialogClose}
        team={editingTeam}
      />

      {/* Detail Dialog */}
      <TeamDetailDialog
        teamId={detailTeamId}
        open={detailDialogOpen}
        onOpenChange={setDetailDialogOpen}
        onEdit={handleEdit}
      />

      {/* Delete Confirmation */}
      <AlertDialog open={!!teamToDelete} onOpenChange={() => setTeamToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Team löschen?</AlertDialogTitle>
            <AlertDialogDescription>
              Möchten Sie das Team <strong>{teamToDelete?.name}</strong> wirklich löschen? Alle
              Mitgliedschaften und geteilten Dokumente werden entfernt. Diese Aktion kann nicht
              rückgängig gemacht werden.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground"
            >
              Löschen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Archive Confirmation */}
      <AlertDialog open={!!teamToArchive} onOpenChange={() => setTeamToArchive(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Team archivieren?</AlertDialogTitle>
            <AlertDialogDescription>
              Möchten Sie das Team <strong>{teamToArchive?.name}</strong> archivieren? Das Team
              wird deaktiviert, bleibt aber erhalten und kann später wiederhergestellt werden.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction onClick={handleArchive}>Archivieren</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
