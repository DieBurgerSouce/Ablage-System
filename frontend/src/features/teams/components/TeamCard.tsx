/**
 * TeamCard Component
 *
 * Karte zur Darstellung eines Teams in der Listenansicht.
 */

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Users,
  FileText,
  MoreVertical,
  Pencil,
  Archive,
  Trash2,
  Eye,
  EyeOff,
  Building2,
  FolderKanban,
  Briefcase,
  Users2,
  Globe,
} from 'lucide-react';
import type { Team, TeamType, TeamStatus, TeamVisibility } from '../api/teams-api';

interface TeamCardProps {
  team: Team;
  onView: (team: Team) => void;
  onEdit: (team: Team) => void;
  onArchive: (team: Team) => void;
  onDelete: (team: Team) => void;
}

const teamTypeConfig: Record<TeamType, { label: string; icon: React.ElementType; color: string }> = {
  department: { label: 'Abteilung', icon: Building2, color: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200' },
  project: { label: 'Projekt', icon: FolderKanban, color: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' },
  working_group: { label: 'Arbeitsgruppe', icon: Users2, color: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200' },
  committee: { label: 'Gremium', icon: Briefcase, color: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200' },
  virtual: { label: 'Virtuell', icon: Globe, color: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200' },
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

export function TeamCard({ team, onView, onEdit, onArchive, onDelete }: TeamCardProps) {
  const typeConfig = teamTypeConfig[team.team_type];
  const TypeIcon = typeConfig.icon;
  const VisibilityIcon = visibilityConfig[team.visibility].icon;

  return (
    <Card
      className="cursor-pointer hover:shadow-md transition-shadow"
      onClick={() => onView(team)}
    >
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <div className={`p-2 rounded-lg ${typeConfig.color}`}>
              <TypeIcon className="h-4 w-4" />
            </div>
            <div>
              <CardTitle className="text-lg">{team.name}</CardTitle>
              <CardDescription className="text-xs mt-0.5">
                {typeConfig.label}
              </CardDescription>
            </div>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
              <Button variant="ghost" size="icon" className="h-8 w-8">
                <MoreVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onEdit(team); }}>
                <Pencil className="h-4 w-4 mr-2" />
                Bearbeiten
              </DropdownMenuItem>
              {team.status !== 'archived' && (
                <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onArchive(team); }}>
                  <Archive className="h-4 w-4 mr-2" />
                  Archivieren
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={(e) => { e.stopPropagation(); onDelete(team); }}
                className="text-destructive"
              >
                <Trash2 className="h-4 w-4 mr-2" />
                Löschen
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </CardHeader>
      <CardContent>
        {team.description && (
          <p className="text-sm text-muted-foreground mb-3 line-clamp-2">
            {team.description}
          </p>
        )}

        <div className="flex items-center gap-4 text-sm text-muted-foreground">
          <div className="flex items-center gap-1">
            <Users className="h-4 w-4" />
            <span>{team.member_count ?? 0} Mitglieder</span>
          </div>
          <div className="flex items-center gap-1">
            <FileText className="h-4 w-4" />
            <span>{team.document_count ?? 0} Dokumente</span>
          </div>
        </div>

        <div className="flex items-center gap-2 mt-3">
          <Badge variant={statusConfig[team.status].variant}>
            {statusConfig[team.status].label}
          </Badge>
          <Badge variant="outline" className="flex items-center gap-1">
            <VisibilityIcon className="h-3 w-3" />
            {visibilityConfig[team.visibility].label}
          </Badge>
        </div>
      </CardContent>
    </Card>
  );
}
