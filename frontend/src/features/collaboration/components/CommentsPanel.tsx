/**
 * CommentsPanel - Kommentar-Bereich für Dokumente
 *
 * Zeigt alle Kommentare zu einem Dokument und ermöglicht
 * das Erstellen neuer Kommentare mit @mentions.
 */

import { useState, useMemo, useCallback } from 'react';
import { MessageSquare, Loader2, Wifi, WifiOff } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import { useComments, useCreateComment, useDeleteComment } from '../hooks/use-comments';
import { CommentItem } from './CommentItem';
import { MentionInput } from './MentionInput';
import type { Comment } from '../types/collaboration.types';
import { toast } from 'sonner';
import { useCommentRealtime, useWebSocket } from '@/lib/websocket';
import { useAuth } from '@/lib/auth/AuthContext';

interface CommentsPanelProps {
  documentId: string;
  onAnnotationClick?: (annotationId: string) => void;
  className?: string;
}

export function CommentsPanel({ documentId, onAnnotationClick, className }: CommentsPanelProps) {
  const { data, isLoading, error, isError } = useComments(documentId);
  const createMutation = useCreateComment();
  const deleteMutation = useDeleteComment(documentId);
  const { user } = useAuth();
  const { state: wsState } = useWebSocket();

  const [newComment, setNewComment] = useState('');
  const [mentions, setMentions] = useState<{ userId: string; userName: string }[]>([]);
  const [replyingTo, setReplyingTo] = useState<string | null>(null);

  // WebSocket Real-Time Updates
  useCommentRealtime(documentId, {
    onNewComment: (event) => {
      // Nur Toast anzeigen wenn es nicht der eigene Kommentar ist
      if (event.payload.user_id !== user?.id) {
        toast.info(`Neuer Kommentar von ${event.payload.user_name || 'Unbekannt'}`, {
          description: String(event.payload.content || '').substring(0, 50) + '...',
        });
      }
    },
    onReply: (event) => {
      if (event.payload.user_id !== user?.id) {
        toast.info(`${event.payload.user_name || 'Jemand'} hat auf einen Kommentar geantwortet`);
      }
    },
    onDelete: () => {
      // Cache wird automatisch invalidiert, keine Aktion nötig
    },
  });

  // Organize comments into threads
  const { rootComments, repliesMap } = useMemo(() => {
    const comments = data?.comments || [];
    const roots: Comment[] = [];
    const replies: Map<string, Comment[]> = new Map();

    for (const comment of comments) {
      if (comment.parentId) {
        const existing = replies.get(comment.parentId) || [];
        replies.set(comment.parentId, [...existing, comment]);
      } else {
        roots.push(comment);
      }
    }

    // Sort roots by date (newest first)
    roots.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());

    // Sort replies by date (oldest first for chronological order)
    for (const [key, value] of replies.entries()) {
      replies.set(
        key,
        value.sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime())
      );
    }

    return { rootComments: roots, repliesMap: replies };
  }, [data?.comments]);

  // Handle submit
  const handleSubmit = useCallback(async () => {
    if (!newComment.trim()) return;

    try {
      await createMutation.mutateAsync({
        documentId,
        content: newComment.trim(),
        mentions,
        parentId: replyingTo || undefined,
      });

      setNewComment('');
      setMentions([]);
      setReplyingTo(null);
      toast.success('Kommentar hinzugefügt');
    } catch (_error) {
      toast.error('Fehler', {
        description: 'Kommentar konnte nicht gespeichert werden.',
      });
    }
  }, [newComment, mentions, replyingTo, documentId, createMutation]);

  // Handle reply
  const handleReply = useCallback((parentId: string) => {
    setReplyingTo(parentId);
  }, []);

  // Handle delete
  const handleDelete = useCallback(
    async (commentId: string) => {
      try {
        await deleteMutation.mutateAsync(commentId);
        toast.success('Kommentar gelöscht');
      } catch (_error) {
        toast.error('Fehler', {
          description: 'Kommentar konnte nicht gelöscht werden.',
        });
      }
    },
    [deleteMutation]
  );

  // Cancel reply
  const cancelReply = useCallback(() => {
    setReplyingTo(null);
  }, []);

  // Loading state
  if (isLoading) {
    return (
      <Card className={className}>
        <CardContent className="py-8">
          <div className="flex items-center justify-center gap-3 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span>Lade Kommentare...</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Error state
  if (isError) {
    return (
      <Card className={className}>
        <CardContent className="py-8">
          <div className="text-center text-destructive">
            <p>Kommentare konnten nicht geladen werden.</p>
            <p className="text-xs mt-1">{(error as Error)?.message}</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  const replyingToComment = replyingTo
    ? data?.comments.find((c) => c.id === replyingTo)
    : null;

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between text-lg">
          <div className="flex items-center gap-2">
            <MessageSquare className="h-5 w-5" />
            Kommentare
            {data?.total ? (
              <span className="text-sm font-normal text-muted-foreground">
                ({data.total})
              </span>
            ) : null}
          </div>
          <div className="flex items-center gap-1">
            {/* WebSocket Status Indicator */}
            <Badge
              variant={wsState === 'connected' ? 'default' : 'secondary'}
              className="gap-1 text-xs"
            >
              {wsState === 'connected' ? (
                <>
                  <Wifi className="h-3 w-3" />
                  Live
                </>
              ) : (
                <>
                  <WifiOff className="h-3 w-3" />
                  Offline
                </>
              )}
            </Badge>
            {onAnnotationClick && (
              <Badge variant="outline" className="gap-1 text-xs">
                <MessageSquare className="h-3 w-3" />
                Annotationen verknuepft
              </Badge>
            )}
          </div>
        </CardTitle>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* New Comment Input */}
        <div className="space-y-2">
          {replyingToComment && (
            <div className="flex items-center justify-between bg-muted/50 px-3 py-2 rounded-md text-sm">
              <span>
                Antwort auf <strong>{replyingToComment.userName}</strong>
              </span>
              <button
                type="button"
                onClick={cancelReply}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                Abbrechen
              </button>
            </div>
          )}
          <MentionInput
            value={newComment}
            onChange={setNewComment}
            onSubmit={handleSubmit}
            isSubmitting={createMutation.isPending}
            mentions={mentions}
            onMentionsChange={setMentions}
            placeholder={
              replyingTo
                ? 'Antwort schreiben...'
                : 'Kommentar schreiben... (@erwähnen)'
            }
          />
        </div>

        <Separator />

        {/* Comments List */}
        {rootComments.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <MessageSquare className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>Noch keine Kommentare.</p>
            <p className="text-xs mt-1">
              Starten Sie die Diskussion mit dem ersten Kommentar.
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            {rootComments.map((comment) => (
              <CommentItem
                key={comment.id}
                comment={comment}
                replies={repliesMap.get(comment.id) || []}
                onReply={handleReply}
                onDelete={handleDelete}
                currentUserId={user?.id || ''}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default CommentsPanel;
