/**
 * CommentThread - Dokumenten-Kommentare mit Antworten
 *
 * Features:
 * - Liste von Kommentaren mit Autor, Zeitstempel, Text
 * - "Kommentar hinzufügen" Input mit Submit
 * - @mention-Anzeige (formatiert als farbiger Text)
 * - Bearbeiten/Löschen eigener Kommentare
 * - Thread-Struktur (Antworten auf Kommentare)
 * - Echtzeit-Updates über WebSocket
 */

import { useState, useRef, useCallback, useMemo } from 'react';
import { Send, MessageSquare, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import { useCommentRealtime } from '@/lib/websocket';
import {
  useComments,
  useCreateComment,
  useUpdateComment as useUpdateCommentMutation,
  useDeleteComment as useDeleteCommentMutation,
} from '../hooks/use-comments';
import { CommentItem } from './CommentItem';
import type { Comment } from '../types/collaboration.types';

// ==================== Sub-Components ====================

interface CommentInputProps {
  onSubmit: (content: string) => void;
  isSubmitting: boolean;
  placeholder?: string;
  autoFocus?: boolean;
  onCancel?: () => void;
}

function CommentInput({
  onSubmit,
  isSubmitting,
  placeholder = 'Kommentar hinzufügen...',
  autoFocus = false,
  onCancel,
}: CommentInputProps) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
    setValue('');
  }, [value, onSubmit]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        handleSubmit();
      }
      if (e.key === 'Escape' && onCancel) {
        onCancel();
      }
    },
    [handleSubmit, onCancel],
  );

  return (
    <div className="flex gap-2">
      <Textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        autoFocus={autoFocus}
        className="min-h-[60px] max-h-[120px] resize-none text-sm"
        disabled={isSubmitting}
      />
      <div className="flex flex-col gap-1">
        <Button
          size="sm"
          className="h-8 px-3"
          onClick={handleSubmit}
          disabled={!value.trim() || isSubmitting}
        >
          {isSubmitting ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Send className="h-3.5 w-3.5" />
          )}
        </Button>
        {onCancel && (
          <Button
            variant="ghost"
            size="sm"
            className="h-8 px-3 text-xs"
            onClick={onCancel}
          >
            Abbrechen
          </Button>
        )}
      </div>
    </div>
  );
}

// ==================== Edit Input ====================

interface EditInputProps {
  initialContent: string;
  onSave: (content: string) => void;
  onCancel: () => void;
  isSaving: boolean;
}

function EditInput({ initialContent, onSave, onCancel, isSaving }: EditInputProps) {
  const [value, setValue] = useState(initialContent);

  const handleSave = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || trimmed === initialContent) {
      onCancel();
      return;
    }
    onSave(trimmed);
  }, [value, initialContent, onSave, onCancel]);

  return (
    <div className="space-y-2">
      <Textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        className="min-h-[60px] max-h-[120px] resize-none text-sm"
        autoFocus
        disabled={isSaving}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            handleSave();
          }
          if (e.key === 'Escape') onCancel();
        }}
      />
      <div className="flex gap-2 justify-end">
        <Button variant="ghost" size="sm" onClick={onCancel} className="h-7 text-xs">
          Abbrechen
        </Button>
        <Button
          size="sm"
          onClick={handleSave}
          disabled={!value.trim() || isSaving}
          className="h-7 text-xs"
        >
          {isSaving ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}
          Speichern
        </Button>
      </div>
    </div>
  );
}

// ==================== Main Component ====================

interface CommentThreadProps {
  /** Dokument-ID */
  documentId: string;
  /** Aktuelle User-ID */
  currentUserId?: string;
  /** Höhe des Scroll-Bereichs */
  height?: string;
  className?: string;
}

export function CommentThread({
  documentId,
  currentUserId,
  height = '400px',
  className,
}: CommentThreadProps) {
  const [replyToId, setReplyToId] = useState<string | null>(null);
  const [editingComment, setEditingComment] = useState<Comment | null>(null);

  // Data Hooks (using existing hooks from use-comments.ts)
  const { data, isLoading, error } = useComments(documentId);
  const addCommentMutation = useCreateComment();
  const updateCommentMutation = useUpdateCommentMutation(documentId);
  const deleteCommentMutation = useDeleteCommentMutation(documentId);

  // Real-time updates via existing global WebSocket
  useCommentRealtime(documentId);

  // Organize comments into threads
  const { topLevel, repliesMap } = useMemo(() => {
    const comments = data?.comments ?? [];
    const top: Comment[] = [];
    const replies: Record<string, Comment[]> = {};

    for (const comment of comments) {
      if (comment.parentId) {
        if (!replies[comment.parentId]) {
          replies[comment.parentId] = [];
        }
        replies[comment.parentId].push(comment);
      } else {
        top.push(comment);
      }
    }

    return { topLevel: top, repliesMap: replies };
  }, [data?.comments]);

  // Handlers
  const handleAddComment = useCallback(
    (content: string) => {
      addCommentMutation.mutate({ documentId, content });
    },
    [addCommentMutation, documentId],
  );

  const handleReply = useCallback(
    (content: string) => {
      if (!replyToId) return;
      addCommentMutation.mutate(
        { documentId, content, parentId: replyToId },
        { onSuccess: () => setReplyToId(null) },
      );
    },
    [replyToId, addCommentMutation, documentId],
  );

  const handleEdit = useCallback(
    (content: string) => {
      if (!editingComment) return;
      updateCommentMutation.mutate(
        { commentId: editingComment.id, payload: { content } },
        { onSuccess: () => setEditingComment(null) },
      );
    },
    [editingComment, updateCommentMutation],
  );

  const handleDelete = useCallback(
    (commentId: string) => {
      deleteCommentMutation.mutate(commentId);
    },
    [deleteCommentMutation],
  );

  // Loading state
  if (isLoading) {
    return (
      <div className={cn('flex items-center justify-center py-8', className)}>
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        <span className="ml-2 text-sm text-muted-foreground">Kommentare werden geladen...</span>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className={cn('flex items-center justify-center py-8 text-destructive', className)}>
        <p className="text-sm">Fehler beim Laden der Kommentare</p>
      </div>
    );
  }

  return (
    <div className={cn('flex flex-col', className)}>
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b">
        <MessageSquare className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-sm font-medium">
          Kommentare
          {data?.total ? ` (${data.total})` : ''}
        </h3>
      </div>

      {/* Comments List */}
      <ScrollArea style={{ height }}>
        <div className="p-3 space-y-4">
          {topLevel.length === 0 && (
            <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
              <MessageSquare className="h-8 w-8 mb-2 opacity-50" />
              <p className="text-sm">Noch keine Kommentare</p>
              <p className="text-xs mt-1">Sei der Erste, der einen Kommentar schreibt</p>
            </div>
          )}

          {topLevel.map((comment) => (
            <div key={comment.id}>
              {/* Comment or Edit Mode */}
              {editingComment?.id === comment.id ? (
                <EditInput
                  initialContent={comment.content}
                  onSave={handleEdit}
                  onCancel={() => setEditingComment(null)}
                  isSaving={updateCommentMutation.isPending}
                />
              ) : (
                <CommentItem
                  comment={comment}
                  replies={repliesMap[comment.id]}
                  onReply={(parentId) => setReplyToId(parentId)}
                  onEdit={(c) => setEditingComment(c)}
                  onDelete={handleDelete}
                  currentUserId={currentUserId}
                />
              )}

              {/* Reply Input */}
              {replyToId === comment.id && (
                <div className="ml-11 mt-2">
                  <CommentInput
                    onSubmit={handleReply}
                    isSubmitting={addCommentMutation.isPending}
                    placeholder="Antwort schreiben..."
                    autoFocus
                    onCancel={() => setReplyToId(null)}
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      </ScrollArea>

      {/* New Comment Input */}
      <div className="border-t p-3">
        <CommentInput
          onSubmit={handleAddComment}
          isSubmitting={addCommentMutation.isPending}
          placeholder="Kommentar hinzufügen... (Strg+Enter zum Senden)"
        />
      </div>
    </div>
  );
}

export default CommentThread;
