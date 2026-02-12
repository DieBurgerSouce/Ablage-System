/**
 * Conversation History Component
 *
 * Vision 2.0 - Phase 1 (Januar 2026)
 *
 * Displays a list of past AI conversations with:
 * - Search and filter functionality
 * - Star/favorite conversations
 * - Delete conversations
 * - Resume previous conversations
 */

import { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  History,
  Star,
  StarOff,
  Trash2,
  Search,
  MessageSquare,
  Zap,
  Calendar,
  Loader2,
  ChevronRight,
  Archive,
  Filter,
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
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
import { cn } from '@/lib/utils';
import {
  useConversations,
  ConversationSummary,
} from '../hooks/use-finance-assistant';
import {
  updateConversation,
  deleteConversation,
} from '@/lib/api/services/finance-assistant';
import { useQueryClient, useMutation } from '@tanstack/react-query';
import { financeAssistantKeys } from '../hooks/use-finance-assistant';

// ===== Types =====

interface ConversationHistoryProps {
  onSelectConversation: (conversation: ConversationSummary) => void;
  onNewConversation: () => void;
  selectedConversationId?: string;
  compact?: boolean;
}

type FilterType = 'all' | 'starred' | 'active' | 'archived';

// ===== Main Component =====

export function ConversationHistory({
  onSelectConversation,
  onNewConversation,
  selectedConversationId,
  compact = false,
}: ConversationHistoryProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [filter, setFilter] = useState<FilterType>('active');
  const [deleteTarget, setDeleteTarget] = useState<ConversationSummary | null>(null);
  const queryClient = useQueryClient();

  // Fetch conversations based on filter
  const { data, isLoading, error } = useConversations({
    isActive: filter === 'active' ? true : filter === 'archived' ? false : undefined,
    isStarred: filter === 'starred' ? true : undefined,
    search: searchQuery || undefined,
    pageSize: 50,
  });

  // Star mutation
  const starMutation = useMutation({
    mutationFn: ({ id, starred }: { id: string; starred: boolean }) =>
      updateConversation(id, { is_starred: starred }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: financeAssistantKeys.conversationsList() });
    },
  });

  // Archive mutation
  const archiveMutation = useMutation({
    mutationFn: (id: string) => updateConversation(id, { is_active: false }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: financeAssistantKeys.conversationsList() });
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: deleteConversation,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: financeAssistantKeys.conversationsList() });
      setDeleteTarget(null);
    },
  });

  const handleStar = useCallback(
    (conversation: ConversationSummary, e: React.MouseEvent) => {
      e.stopPropagation();
      starMutation.mutate({ id: conversation.id, starred: !conversation.is_starred });
    },
    [starMutation]
  );

  const handleArchive = useCallback(
    (conversation: ConversationSummary, e: React.MouseEvent) => {
      e.stopPropagation();
      archiveMutation.mutate(conversation.id);
    },
    [archiveMutation]
  );

  const handleDelete = useCallback((conversation: ConversationSummary, e: React.MouseEvent) => {
    e.stopPropagation();
    setDeleteTarget(conversation);
  }, []);

  const confirmDelete = useCallback(() => {
    if (deleteTarget) {
      deleteMutation.mutate(deleteTarget.id);
    }
  }, [deleteTarget, deleteMutation]);

  const conversations = data?.conversations ?? [];

  const filterLabels: Record<FilterType, string> = {
    all: 'Alle',
    starred: 'Favoriten',
    active: 'Aktiv',
    archived: 'Archiviert',
  };

  return (
    <div className={cn('flex flex-col h-full', compact && 'max-h-[400px]')}>
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b">
        <div className="flex items-center gap-2">
          <History className="h-4 w-4 text-muted-foreground" />
          <span className="font-medium text-sm">Verlauf</span>
          {data?.total !== undefined && (
            <Badge variant="secondary" className="text-xs">
              {data.total}
            </Badge>
          )}
        </div>
        <Button variant="outline" size="sm" onClick={onNewConversation}>
          Neue Konversation
        </Button>
      </div>

      {/* Search and Filter */}
      <div className="p-3 space-y-2 border-b">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Konversation suchen..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-8 h-8 text-sm"
          />
        </div>
        <div className="flex gap-1">
          {(['active', 'starred', 'archived', 'all'] as FilterType[]).map((f) => (
            <Button
              key={f}
              variant={filter === f ? 'default' : 'ghost'}
              size="sm"
              className="h-7 text-xs"
              onClick={() => setFilter(f)}
            >
              {filterLabels[f]}
            </Button>
          ))}
        </div>
      </div>

      {/* Conversation List */}
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {isLoading && (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          )}

          {error && (
            <div className="text-center py-8 text-sm text-destructive">
              Fehler beim Laden der Konversationen
            </div>
          )}

          {!isLoading && conversations.length === 0 && (
            <div className="text-center py-8">
              <MessageSquare className="h-8 w-8 mx-auto text-muted-foreground/50 mb-2" />
              <p className="text-sm text-muted-foreground">
                {searchQuery
                  ? 'Keine Konversationen gefunden'
                  : 'Noch keine Konversationen'}
              </p>
            </div>
          )}

          <AnimatePresence mode="popLayout">
            {conversations.map((conversation) => (
              <ConversationItem
                key={conversation.id}
                conversation={conversation}
                isSelected={conversation.id === selectedConversationId}
                onSelect={() => onSelectConversation(conversation)}
                onStar={(e) => handleStar(conversation, e)}
                onArchive={(e) => handleArchive(conversation, e)}
                onDelete={(e) => handleDelete(conversation, e)}
                compact={compact}
              />
            ))}
          </AnimatePresence>
        </div>
      </ScrollArea>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Konversation löschen?</AlertDialogTitle>
            <AlertDialogDescription>
              Diese Aktion kann nicht rückgängig gemacht werden. Die Konversation
              und alle zugehörigen Nachrichten werden dauerhaft gelöscht.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Trash2 className="h-4 w-4 mr-2" />
              )}
              Löschen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// ===== Conversation Item Component =====

interface ConversationItemProps {
  conversation: ConversationSummary;
  isSelected: boolean;
  onSelect: () => void;
  onStar: (e: React.MouseEvent) => void;
  onArchive: (e: React.MouseEvent) => void;
  onDelete: (e: React.MouseEvent) => void;
  compact?: boolean;
}

function ConversationItem({
  conversation,
  isSelected,
  onSelect,
  onStar,
  onArchive,
  onDelete,
  compact,
}: ConversationItemProps) {
  const title =
    conversation.title ||
    (conversation.context_page
      ? `Konversation auf ${conversation.context_page}`
      : 'Neue Konversation');

  const timeAgo = conversation.last_message_at
    ? formatDistanceToNow(new Date(conversation.last_message_at), {
        addSuffix: true,
        locale: de,
      })
    : formatDistanceToNow(new Date(conversation.created_at), {
        addSuffix: true,
        locale: de,
      });

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: -20 }}
      transition={{ duration: 0.15 }}
    >
      <button
        onClick={onSelect}
        className={cn(
          'w-full flex items-start gap-3 p-2.5 rounded-lg text-left transition-colors group',
          'hover:bg-muted/50',
          isSelected && 'bg-primary/10 border border-primary/20'
        )}
      >
        {/* Star indicator */}
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={onStar}
                className={cn(
                  'mt-0.5 p-0.5 rounded transition-colors',
                  conversation.is_starred
                    ? 'text-yellow-500'
                    : 'text-muted-foreground/30 hover:text-muted-foreground'
                )}
              >
                {conversation.is_starred ? (
                  <Star className="h-4 w-4 fill-current" />
                ) : (
                  <StarOff className="h-4 w-4" />
                )}
              </button>
            </TooltipTrigger>
            <TooltipContent>
              {conversation.is_starred ? 'Aus Favoriten entfernen' : 'Zu Favoriten hinzufügen'}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-sm truncate">{title}</span>
            {!conversation.is_active && (
              <Badge variant="outline" className="text-[10px] py-0">
                Archiviert
              </Badge>
            )}
          </div>

          {!compact && (
            <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <MessageSquare className="h-3 w-3" />
                {conversation.message_count}
              </span>
              {conversation.action_count > 0 && (
                <span className="flex items-center gap-1">
                  <Zap className="h-3 w-3" />
                  {conversation.action_count}
                </span>
              )}
              <span className="flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                {timeAgo}
              </span>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={(e) => e.stopPropagation()}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={onStar}>
                <Star className="h-4 w-4 mr-2" />
                {conversation.is_starred ? 'Favorit entfernen' : 'Als Favorit'}
              </DropdownMenuItem>
              {conversation.is_active && (
                <DropdownMenuItem onClick={onArchive}>
                  <Archive className="h-4 w-4 mr-2" />
                  Archivieren
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={onDelete} className="text-destructive">
                <Trash2 className="h-4 w-4 mr-2" />
                Löschen
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </button>
    </motion.div>
  );
}

export default ConversationHistory;
