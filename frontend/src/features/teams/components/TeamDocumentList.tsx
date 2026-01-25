/**
 * TeamDocumentList Component
 *
 * Zeigt mit dem Team geteilte Dokumente an.
 */

import { useState } from 'react';
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
import {
  FileText,
  MoreHorizontal,
  Eye,
  Pencil,
  Trash2,
  ExternalLink,
  FolderOpen,
  Clock,
  User,
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';
import { Link } from '@tanstack/react-router';
import { TeamDocument, TeamDocumentPermission } from '../api/teams-api';
import { useTeamDocuments, useUnshareDocument, useUpdateDocumentShare } from '../hooks/use-teams';

interface TeamDocumentListProps {
  teamId: string;
  isTeamAdmin?: boolean;
}

const permissionConfig: Record<TeamDocumentPermission, { label: string; icon: React.ElementType; color: string }> = {
  view: { label: 'Ansehen', icon: Eye, color: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200' },
  edit: { label: 'Bearbeiten', icon: Pencil, color: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200' },
  full: { label: 'Vollzugriff', icon: FolderOpen, color: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' },
};

export function TeamDocumentList({ teamId, isTeamAdmin = false }: TeamDocumentListProps) {
  const { data: documents, isLoading } = useTeamDocuments(teamId);
  const unshareDocument = useUnshareDocument(teamId);
  const updateShare = useUpdateDocumentShare(teamId);

  const [documentToUnshare, setDocumentToUnshare] = useState<TeamDocument | null>(null);

  const handleUnshare = () => {
    if (documentToUnshare) {
      unshareDocument.mutate(documentToUnshare.document_id);
      setDocumentToUnshare(null);
    }
  };

  const handlePermissionChange = (documentId: string, permission: TeamDocumentPermission) => {
    updateShare.mutate({ documentId, data: { permission } });
  };

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex items-center gap-3 p-3 border rounded-lg">
            <Skeleton className="h-10 w-10 rounded" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-3 w-32" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (!documents || documents.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <FileText className="h-12 w-12 mx-auto mb-2 opacity-50" />
        <p>Keine geteilten Dokumente</p>
        <p className="text-sm mt-1">
          Teilen Sie Dokumente mit diesem Team, um sie hier anzuzeigen.
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="space-y-2">
        {documents.map((doc) => {
          const config = permissionConfig[doc.permission];
          const PermIcon = config.icon;

          return (
            <div
              key={doc.id}
              className="flex items-center justify-between p-3 border rounded-lg hover:bg-muted/50 transition-colors"
            >
              <div className="flex items-center gap-3 min-w-0 flex-1">
                <div className="p-2 rounded bg-muted">
                  <FileText className="h-5 w-5 text-muted-foreground" />
                </div>
                <div className="min-w-0 flex-1">
                  <Link
                    to="/documents/$documentId"
                    params={{ documentId: doc.document_id }}
                    className="font-medium hover:underline truncate block"
                  >
                    {doc.document?.title || 'Unbenanntes Dokument'}
                  </Link>
                  <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
                    {doc.document?.document_type && (
                      <span className="flex items-center gap-1">
                        {doc.document.document_type}
                      </span>
                    )}
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {formatDistanceToNow(new Date(doc.shared_at), {
                        addSuffix: true,
                        locale: de,
                      })}
                    </span>
                    {doc.shared_by && (
                      <span className="flex items-center gap-1">
                        <User className="h-3 w-3" />
                        {doc.shared_by.full_name || doc.shared_by.username}
                      </span>
                    )}
                  </div>
                  {doc.notes && (
                    <p className="text-xs text-muted-foreground mt-1 truncate">{doc.notes}</p>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-2">
                <Badge className={config.color}>
                  <PermIcon className="h-3 w-3 mr-1" />
                  {config.label}
                </Badge>

                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" className="h-8 w-8">
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem asChild>
                      <Link
                        to="/documents/$documentId"
                        params={{ documentId: doc.document_id }}
                      >
                        <ExternalLink className="h-4 w-4 mr-2" />
                        Dokument oeffnen
                      </Link>
                    </DropdownMenuItem>

                    {isTeamAdmin && (
                      <>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          onClick={() => handlePermissionChange(doc.document_id, 'view')}
                          disabled={doc.permission === 'view'}
                        >
                          <Eye className="h-4 w-4 mr-2" />
                          Nur Ansehen
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onClick={() => handlePermissionChange(doc.document_id, 'edit')}
                          disabled={doc.permission === 'edit'}
                        >
                          <Pencil className="h-4 w-4 mr-2" />
                          Bearbeiten erlauben
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onClick={() => handlePermissionChange(doc.document_id, 'full')}
                          disabled={doc.permission === 'full'}
                        >
                          <FolderOpen className="h-4 w-4 mr-2" />
                          Vollzugriff
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          onClick={() => setDocumentToUnshare(doc)}
                          className="text-destructive"
                        >
                          <Trash2 className="h-4 w-4 mr-2" />
                          Freigabe aufheben
                        </DropdownMenuItem>
                      </>
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </div>
          );
        })}
      </div>

      {/* Unshare Confirmation */}
      <AlertDialog open={!!documentToUnshare} onOpenChange={() => setDocumentToUnshare(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Freigabe aufheben?</AlertDialogTitle>
            <AlertDialogDescription>
              Moechten Sie die Freigabe von{' '}
              <strong>{documentToUnshare?.document?.title || 'diesem Dokument'}</strong> wirklich
              aufheben? Das Team hat dann keinen Zugriff mehr auf dieses Dokument.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction onClick={handleUnshare} className="bg-destructive text-destructive-foreground">
              Freigabe aufheben
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
