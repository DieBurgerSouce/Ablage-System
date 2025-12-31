/**
 * CommentItem - Einzelner Kommentar mit Antworten
 *
 * Zeigt einen Kommentar mit:
 * - Benutzerinfo und Zeitstempel
 * - Formatierten Inhalt mit Mentions
 * - Reaktionen
 * - Antworten (verschachtelt)
 * - Aktionen (Antworten, Bearbeiten, Loeschen)
 */

import { useState } from 'react';
import {
  Reply,
  MoreHorizontal,
  Edit2,
  Trash2,
  ThumbsUp,
} from 'lucide-react';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { Comment } from '../types/collaboration.types';
import { cn } from '@/lib/utils';
import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';

interface CommentItemProps {
  comment: Comment;
  replies?: Comment[];
  onReply?: (parentId: string) => void;
  onEdit?: (comment: Comment) => void;
  onDelete?: (commentId: string) => void;
  isNested?: boolean;
  currentUserId?: string;
}

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

function formatContent(content: string, mentions: Comment['mentions']): React.ReactNode {
  if (mentions.length === 0) return content;

  // Sort mentions by startIndex descending to replace from end
  const sortedMentions = [...mentions].sort((a, b) => b.startIndex - a.startIndex);

  const formattedContent = content;
  const parts: (string | React.ReactNode)[] = [];
  let lastIndex = content.length;

  for (const mention of sortedMentions) {
    // Add text after mention
    if (mention.endIndex < lastIndex) {
      parts.unshift(content.slice(mention.endIndex, lastIndex));
    }
    // Add formatted mention
    parts.unshift(
      <span key={mention.userId} className="text-primary font-medium">
        @{mention.userName}
      </span>
    );
    lastIndex = mention.startIndex;
  }

  // Add remaining text at start
  if (lastIndex > 0) {
    parts.unshift(content.slice(0, lastIndex));
  }

  return parts;
}

export function CommentItem({
  comment,
  replies = [],
  onReply,
  onEdit,
  onDelete,
  isNested = false,
  currentUserId,
}: CommentItemProps) {
  const [showReplies, setShowReplies] = useState(true);
  const isOwner = currentUserId === comment.userId;

  const timeAgo = formatDistanceToNow(new Date(comment.createdAt), {
    addSuffix: true,
    locale: de,
  });

  return (
    <div className={cn('group', isNested && 'ml-8 pl-4 border-l-2 border-muted')}>
      <div className="flex gap-3">
        {/* Avatar */}
        <Avatar className="h-8 w-8">
          <AvatarImage src={comment.userAvatar} alt={comment.userName} />
          <AvatarFallback className="text-xs">
            {getInitials(comment.userName)}
          </AvatarFallback>
        </Avatar>

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Header */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-sm">{comment.userName}</span>
            <span className="text-xs text-muted-foreground">{timeAgo}</span>
            {comment.isEdited && (
              <Badge variant="outline" className="text-[10px] px-1 py-0">
                bearbeitet
              </Badge>
            )}
          </div>

          {/* Body */}
          <p className="text-sm mt-1 whitespace-pre-wrap">
            {formatContent(comment.content, comment.mentions)}
          </p>

          {/* Reactions */}
          {comment.reactions && comment.reactions.length > 0 && (
            <div className="flex gap-1 mt-2">
              {comment.reactions.map((reaction) => (
                <Button
                  key={reaction.emoji}
                  variant="ghost"
                  size="sm"
                  className="h-6 px-2 text-xs"
                >
                  {reaction.emoji} {reaction.count}
                </Button>
              ))}
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-1 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs text-muted-foreground"
              onClick={() => onReply?.(comment.id)}
            >
              <Reply className="h-3.5 w-3.5 mr-1" />
              Antworten
            </Button>

            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-muted-foreground"
            >
              <ThumbsUp className="h-3.5 w-3.5" />
            </Button>

            {isOwner && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2 text-muted-foreground"
                  >
                    <MoreHorizontal className="h-3.5 w-3.5" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start">
                  <DropdownMenuItem onClick={() => onEdit?.(comment)}>
                    <Edit2 className="h-4 w-4 mr-2" />
                    Bearbeiten
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    className="text-destructive"
                    onClick={() => onDelete?.(comment.id)}
                  >
                    <Trash2 className="h-4 w-4 mr-2" />
                    Loeschen
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </div>
        </div>
      </div>

      {/* Replies */}
      {replies.length > 0 && (
        <div className="mt-4 space-y-4">
          {!showReplies && (
            <Button
              variant="ghost"
              size="sm"
              className="ml-11 text-xs text-muted-foreground"
              onClick={() => setShowReplies(true)}
            >
              {replies.length} Antwort{replies.length > 1 ? 'en' : ''} anzeigen
            </Button>
          )}
          {showReplies &&
            replies.map((reply) => (
              <CommentItem
                key={reply.id}
                comment={reply}
                onReply={onReply}
                onEdit={onEdit}
                onDelete={onDelete}
                isNested
                currentUserId={currentUserId}
              />
            ))}
        </div>
      )}
    </div>
  );
}

export default CommentItem;
