/**
 * VersionList Component
 *
 * Liste aller Versionen eines Workflows mit Status und Aktionen.
 */

import { useState } from 'react';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';
import {
  MoreHorizontal,
  Play,
  RotateCcw,
  Archive,
  AlertTriangle,
  GitBranch,
  CheckCircle2,
  XCircle,
  Clock,
} from 'lucide-react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Skeleton } from '@/components/ui/skeleton';
import { VersionBadge, VersionNumberBadge } from './VersionBadge';
import type { WorkflowVersion } from '../types/version-types';
import {
  usePublishVersion,
  useDeprecateVersion,
  useArchiveVersion,
} from '../hooks/useWorkflowVersions';
import { formatChangeType } from '@/lib/api/services/workflow-versions';
import { cn } from '@/lib/utils';

interface VersionListProps {
  versions: WorkflowVersion[];
  workflowId: string;
  isLoading?: boolean;
  onSelectVersion: (version: WorkflowVersion) => void;
  onCompareVersions: (versionA: WorkflowVersion, versionB: WorkflowVersion) => void;
  onRollback: (version: WorkflowVersion) => void;
  selectedVersionId?: string;
}

export function VersionList({
  versions,
  workflowId,
  isLoading,
  onSelectVersion,
  onCompareVersions,
  onRollback,
  selectedVersionId,
}: VersionListProps) {
  const [compareMode, setCompareMode] = useState(false);
  const [compareVersionA, setCompareVersionA] = useState<WorkflowVersion | null>(null);

  const publishMutation = usePublishVersion();
  const deprecateMutation = useDeprecateVersion();
  const archiveMutation = useArchiveVersion();

  const handlePublish = (version: WorkflowVersion) => {
    publishMutation.mutate({
      workflowId,
      versionId: version.id,
    });
  };

  const handleDeprecate = (version: WorkflowVersion) => {
    deprecateMutation.mutate({
      workflowId,
      versionId: version.id,
    });
  };

  const handleArchive = (version: WorkflowVersion) => {
    archiveMutation.mutate({
      workflowId,
      versionId: version.id,
    });
  };

  const handleCompareClick = (version: WorkflowVersion) => {
    if (!compareMode) {
      setCompareMode(true);
      setCompareVersionA(version);
    } else if (compareVersionA) {
      onCompareVersions(compareVersionA, version);
      setCompareMode(false);
      setCompareVersionA(null);
    }
  };

  const cancelCompareMode = () => {
    setCompareMode(false);
    setCompareVersionA(null);
  };

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[...Array(5)].map((_, i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    );
  }

  if (versions.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <GitBranch className="h-12 w-12 mx-auto mb-4 opacity-50" />
        <p>Keine Versionen vorhanden</p>
        <p className="text-sm mt-1">
          Erstellen Sie eine neue Version, um die Versionierung zu starten.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {compareMode && (
        <div className="flex items-center justify-between p-3 bg-muted rounded-lg">
          <div className="flex items-center gap-2">
            <GitBranch className="h-4 w-4" />
            <span className="text-sm">
              Vergleichsmodus: Waehlen Sie eine zweite Version zum Vergleich
              {compareVersionA && (
                <span className="font-medium ml-1">
                  (v{compareVersionA.version} ausgewaehlt)
                </span>
              )}
            </span>
          </div>
          <Button variant="ghost" size="sm" onClick={cancelCompareMode}>
            Abbrechen
          </Button>
        </div>
      )}

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[150px]">Version</TableHead>
            <TableHead>Beschreibung</TableHead>
            <TableHead className="w-[100px]">Status</TableHead>
            <TableHead className="w-[100px]">Typ</TableHead>
            <TableHead className="w-[120px] text-right">Erfolgsrate</TableHead>
            <TableHead className="w-[120px] text-right">Ausfuehrungen</TableHead>
            <TableHead className="w-[150px]">Erstellt</TableHead>
            <TableHead className="w-[50px]" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {versions.map((version) => (
            <TableRow
              key={version.id}
              className={cn(
                'cursor-pointer hover:bg-muted/50',
                selectedVersionId === version.id && 'bg-muted',
                compareMode && compareVersionA?.id === version.id && 'bg-primary/10'
              )}
              onClick={() => {
                if (compareMode) {
                  handleCompareClick(version);
                } else {
                  onSelectVersion(version);
                }
              }}
            >
              <TableCell>
                <VersionNumberBadge
                  version={version.version}
                  isActive={version.is_active}
                  isLatest={version.is_latest}
                />
              </TableCell>
              <TableCell>
                <div className="max-w-[300px] truncate">
                  {version.change_description}
                </div>
              </TableCell>
              <TableCell>
                <VersionBadge status={version.status} />
              </TableCell>
              <TableCell>
                <span className="text-sm text-muted-foreground">
                  {formatChangeType(version.change_type)}
                </span>
              </TableCell>
              <TableCell className="text-right">
                <div className="flex items-center justify-end gap-1">
                  {version.execution_count > 0 ? (
                    <>
                      {version.success_rate >= 90 ? (
                        <CheckCircle2 className="h-4 w-4 text-green-500" />
                      ) : version.success_rate >= 70 ? (
                        <Clock className="h-4 w-4 text-yellow-500" />
                      ) : (
                        <XCircle className="h-4 w-4 text-red-500" />
                      )}
                      <span>{version.success_rate.toFixed(1)}%</span>
                    </>
                  ) : (
                    <span className="text-muted-foreground">-</span>
                  )}
                </div>
              </TableCell>
              <TableCell className="text-right">
                {version.execution_count > 0 ? (
                  <span>{version.execution_count.toLocaleString('de-DE')}</span>
                ) : (
                  <span className="text-muted-foreground">-</span>
                )}
              </TableCell>
              <TableCell>
                <span className="text-sm text-muted-foreground">
                  {format(new Date(version.created_at), 'dd.MM.yyyy HH:mm', {
                    locale: de,
                  })}
                </span>
              </TableCell>
              <TableCell>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    {version.status === 'draft' && (
                      <DropdownMenuItem
                        onClick={(e) => {
                          e.stopPropagation();
                          handlePublish(version);
                        }}
                      >
                        <Play className="h-4 w-4 mr-2" />
                        Veroeffentlichen
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuItem
                      onClick={(e) => {
                        e.stopPropagation();
                        handleCompareClick(version);
                      }}
                    >
                      <GitBranch className="h-4 w-4 mr-2" />
                      Vergleichen
                    </DropdownMenuItem>
                    {version.status !== 'active' && (
                      <DropdownMenuItem
                        onClick={(e) => {
                          e.stopPropagation();
                          onRollback(version);
                        }}
                      >
                        <RotateCcw className="h-4 w-4 mr-2" />
                        Rollback zu dieser Version
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuSeparator />
                    {version.status === 'active' && (
                      <DropdownMenuItem
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeprecate(version);
                        }}
                        className="text-destructive"
                      >
                        <AlertTriangle className="h-4 w-4 mr-2" />
                        Als veraltet markieren
                      </DropdownMenuItem>
                    )}
                    {version.status !== 'archived' && version.status !== 'active' && (
                      <DropdownMenuItem
                        onClick={(e) => {
                          e.stopPropagation();
                          handleArchive(version);
                        }}
                      >
                        <Archive className="h-4 w-4 mr-2" />
                        Archivieren
                      </DropdownMenuItem>
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
