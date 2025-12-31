/**
 * PrivatSpaceList - Liste aller Privat-Bereiche
 *
 * Zeigt persönliche und geteilte Bereiche des Nutzers
 */

import * as React from 'react';
import { Link } from '@tanstack/react-router';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Plus,
  MoreHorizontal,
  Lock,
  Users,
  FolderOpen,
  FileText,
  Settings,
  Trash2,
  HardDrive,
} from 'lucide-react';
import type { PrivatSpaceWithStats, PrivatSpaceType } from '@/types/privat';
import { cn } from '@/lib/utils';

interface PrivatSpaceListProps {
  spaces: PrivatSpaceWithStats[];
  isLoading?: boolean;
  error?: Error | null;
  onCreate?: () => void;
  onEdit?: (space: PrivatSpaceWithStats) => void;
  onDelete?: (space: PrivatSpaceWithStats) => void | Promise<void>;
  onSettings?: (space: PrivatSpaceWithStats) => void;
  className?: string;
}

const formatBytes = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
};

export function PrivatSpaceList({
  spaces,
  isLoading,
  error,
  onCreate,
  onEdit,
  onDelete,
  onSettings,
  className,
}: PrivatSpaceListProps) {
  if (error) {
    return (
      <Card className={className} role="alert" aria-live="polite">
        <CardHeader>
          <CardTitle>Meine Bereiche</CardTitle>
          <CardDescription className="text-destructive">
            Fehler beim Laden der Bereiche
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const personalSpaces = spaces.filter((s) => s.spaceType === 'personal');
  const sharedSpaces = spaces.filter((s) => s.spaceType === 'shared');

  return (
    <div
      className={cn('space-y-6', className)}
      role="region"
      aria-label="Bereichsverwaltung"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight" id="spaces-heading">
            Meine Bereiche
          </h1>
          <p className="text-muted-foreground" id="spaces-description">
            Verwalten Sie Ihre persönlichen und geteilten Dokumentenbereiche
          </p>
        </div>
        {onCreate && (
          <Button
            onClick={onCreate}
            aria-describedby="spaces-description"
          >
            <Plus className="mr-2 h-4 w-4" aria-hidden="true" />
            Neuer Bereich
          </Button>
        )}
      </div>

      {isLoading ? (
        <div
          className="grid gap-4 md:grid-cols-2 lg:grid-cols-3"
          aria-busy="true"
          aria-label="Bereiche werden geladen"
        >
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-48" aria-hidden="true" />
          ))}
        </div>
      ) : spaces.length === 0 ? (
        <Card role="status" aria-live="polite">
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Lock className="h-12 w-12 text-muted-foreground mb-4" aria-hidden="true" />
            <h3 className="text-lg font-medium mb-2">Noch keine Bereiche</h3>
            <p className="text-muted-foreground text-center mb-4">
              Erstellen Sie Ihren ersten persönlichen Bereich, um Dokumente sicher zu speichern.
            </p>
            {onCreate && (
              <Button onClick={onCreate}>
                <Plus className="mr-2 h-4 w-4" aria-hidden="true" />
                Bereich erstellen
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Personal Spaces */}
          {personalSpaces.length > 0 && (
            <section aria-labelledby="personal-spaces-heading">
              <h3
                id="personal-spaces-heading"
                className="text-lg font-semibold mb-4 flex items-center gap-2"
              >
                <Lock className="h-5 w-5 text-purple-500" aria-hidden="true" />
                Persönliche Bereiche
                <span className="sr-only">({personalSpaces.length} Bereiche)</span>
              </h3>
              <div
                className="grid gap-4 md:grid-cols-2 lg:grid-cols-3"
                role="list"
                aria-label="Liste persönlicher Bereiche"
              >
                {personalSpaces.map((space) => (
                  <SpaceCard
                    key={space.id}
                    space={space}
                    onEdit={onEdit}
                    onDelete={onDelete}
                    onSettings={onSettings}
                  />
                ))}
              </div>
            </section>
          )}

          {/* Shared Spaces */}
          {sharedSpaces.length > 0 && (
            <section aria-labelledby="shared-spaces-heading">
              <h3
                id="shared-spaces-heading"
                className="text-lg font-semibold mb-4 flex items-center gap-2"
              >
                <Users className="h-5 w-5 text-blue-500" aria-hidden="true" />
                Geteilte Bereiche
                <span className="sr-only">({sharedSpaces.length} Bereiche)</span>
              </h3>
              <div
                className="grid gap-4 md:grid-cols-2 lg:grid-cols-3"
                role="list"
                aria-label="Liste geteilter Bereiche"
              >
                {sharedSpaces.map((space) => (
                  <SpaceCard
                    key={space.id}
                    space={space}
                    onEdit={onEdit}
                    onDelete={onDelete}
                    onSettings={onSettings}
                  />
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}

interface SpaceCardProps {
  space: PrivatSpaceWithStats;
  onEdit?: (space: PrivatSpaceWithStats) => void;
  onDelete?: (space: PrivatSpaceWithStats) => void;
  onSettings?: (space: PrivatSpaceWithStats) => void;
}

function SpaceCard({ space, onEdit, onDelete, onSettings }: SpaceCardProps) {
  const isPersonal = space.spaceType === 'personal';
  const spaceTypeLabel = isPersonal ? 'Persönlicher Bereich' : 'Geteilter Bereich';

  return (
    <Card
      className="hover:shadow-md transition-shadow focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2"
      role="listitem"
      aria-label={`${spaceTypeLabel}: ${space.name}`}
    >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div
              className={cn(
                'p-2 rounded-lg',
                isPersonal ? 'bg-purple-100 dark:bg-purple-950' : 'bg-blue-100 dark:bg-blue-950'
              )}
              aria-hidden="true"
            >
              {isPersonal ? (
                <Lock className="h-5 w-5 text-purple-600 dark:text-purple-400" />
              ) : (
                <Users className="h-5 w-5 text-blue-600 dark:text-blue-400" />
              )}
            </div>
            <div>
              <CardTitle className="text-base">
                <Link
                  to="/privat/spaces/$spaceId"
                  params={{ spaceId: space.id }}
                  className="hover:underline focus:outline-none focus:underline"
                  aria-label={`Bereich "${space.name}" öffnen`}
                >
                  {space.name}
                </Link>
              </CardTitle>
              {space.description && (
                <CardDescription className="line-clamp-1">
                  {space.description}
                </CardDescription>
              )}
            </div>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                aria-label={`Aktionen für Bereich "${space.name}"`}
              >
                <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => onSettings?.(space)}>
                <Settings className="mr-2 h-4 w-4" aria-hidden="true" />
                Einstellungen
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onEdit?.(space)}>
                <FolderOpen className="mr-2 h-4 w-4" aria-hidden="true" />
                Bearbeiten
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={() => onDelete?.(space)}
                className="text-destructive"
              >
                <Trash2 className="mr-2 h-4 w-4" aria-hidden="true" />
                Löschen
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-2 gap-4 text-sm">
          <div className="flex items-center gap-2 text-muted-foreground">
            <FileText className="h-4 w-4" aria-hidden="true" />
            <dt className="sr-only">Anzahl Dokumente</dt>
            <dd>{space.documentCount} Dokumente</dd>
          </div>
          <div className="flex items-center gap-2 text-muted-foreground">
            <FolderOpen className="h-4 w-4" aria-hidden="true" />
            <dt className="sr-only">Anzahl Ordner</dt>
            <dd>{space.folderCount} Ordner</dd>
          </div>
          <div className="flex items-center gap-2 text-muted-foreground">
            <HardDrive className="h-4 w-4" aria-hidden="true" />
            <dt className="sr-only">Speichergröße</dt>
            <dd>{formatBytes(space.totalSize)}</dd>
          </div>
          {!isPersonal && (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Users className="h-4 w-4" aria-hidden="true" />
              <dt className="sr-only">Anzahl Nutzer</dt>
              <dd>{space.accessCount} Nutzer</dd>
            </div>
          )}
        </dl>
        <div className="mt-4">
          <Link to="/privat/spaces/$spaceId" params={{ spaceId: space.id }}>
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              aria-label={`Bereich "${space.name}" öffnen`}
            >
              Öffnen
            </Button>
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}

export default PrivatSpaceList;
