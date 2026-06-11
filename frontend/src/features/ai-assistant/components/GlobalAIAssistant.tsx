/**
 * Global AI Assistant Widget
 *
 * Floating AI assistant available on every page.
 * Features:
 * - Minimized/Expanded/Fullscreen modes
 * - Context-aware suggestions
 * - Keyboard shortcuts (Ctrl+K)
 * - WebSocket-based streaming chat
 * - Role-based AI actions (Viewer/Editor/Admin)
 */

import { useEffect, useCallback, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Bot,
  X,
  Minimize2,
  Maximize2,
  Sparkles,
  Loader2,
  Send,
  FileText,
  AlertCircle,
  Wifi,
  WifiOff,
  Zap,
  Shield,
  Eye,
  Edit3,
  CheckCircle,
  XCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Input } from '@/components/ui/input';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { logger } from '@/lib/logger';

import { useAIAssistantStore } from '../stores/ai-assistant-store';
import { usePageContext, getContextSuggestions, getContextPlaceholder } from '../hooks/use-page-context';
import {
  useContextAwareAction,
  AIActionType,
  AIActionAutonomyLevel,
  AIActionStatus,
  ACTION_METADATA,
  type AIActionSuggestion,
} from '../hooks/use-ai-actions';
import { useChatWebSocket } from '@/features/rag/hooks/use-chat-websocket';
import { ChatMessage as ChatMessageComponent } from '@/features/rag/components/ChatMessage';
import type { ConnectionStatus } from '@/features/rag/types/chat-types';

// ==================== Constants ====================

const KEYBOARD_SHORTCUT = 'k';
const WIDGET_WIDTH = 420;
const WIDGET_HEIGHT = 600;
const MINIMIZED_SIZE = 56;

// ==================== Sub-Components ====================

interface QuickSuggestionProps {
  suggestion: string;
  onClick: () => void;
}

function QuickSuggestion({ suggestion, onClick }: QuickSuggestionProps) {
  return (
    <button
      onClick={onClick}
      className="px-3 py-1.5 text-xs bg-primary/10 hover:bg-primary/20 text-primary rounded-full transition-colors whitespace-nowrap"
    >
      {suggestion}
    </button>
  );
}

interface ConnectionStatusIndicatorProps {
  status: ConnectionStatus;
}

function ConnectionStatusIndicator({ status }: ConnectionStatusIndicatorProps) {
  const config = {
    connected: { icon: Wifi, color: 'text-green-500', label: 'Verbunden' },
    connecting: { icon: Loader2, color: 'text-yellow-500', label: 'Verbinde...' },
    disconnected: { icon: WifiOff, color: 'text-muted-foreground', label: 'Getrennt' },
    error: { icon: AlertCircle, color: 'text-destructive', label: 'Fehler' },
  };

  const { icon: Icon, color, label } = config[status];

  return (
    <div className={cn('flex items-center gap-1 text-xs', color)}>
      <Icon className={cn('h-3 w-3', status === 'connecting' && 'animate-spin')} />
      <span>{label}</span>
    </div>
  );
}

// Autonomy Level Badge
interface AutonomyLevelBadgeProps {
  level: AIActionAutonomyLevel;
}

function AutonomyLevelBadge({ level }: AutonomyLevelBadgeProps) {
  const config = {
    [AIActionAutonomyLevel.VIEWER]: {
      icon: Eye,
      label: 'Viewer',
      description: 'Nur lesen',
      variant: 'secondary' as const,
    },
    [AIActionAutonomyLevel.EDITOR]: {
      icon: Edit3,
      label: 'Editor',
      description: 'Mit Bestätigung',
      variant: 'default' as const,
    },
    [AIActionAutonomyLevel.ADMIN]: {
      icon: Shield,
      label: 'Admin',
      description: 'Volle Autonomie',
      variant: 'destructive' as const,
    },
  };

  const { icon: Icon, label, description, variant } = config[level];

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge variant={variant} className="text-xs gap-1 cursor-help">
            <Icon className="h-3 w-3" />
            {label}
          </Badge>
        </TooltipTrigger>
        <TooltipContent>
          <p className="font-medium">{label} Modus</p>
          <p className="text-xs text-muted-foreground">{description}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

// Action Suggestion Card (for Editor-level confirmation)
interface ActionSuggestionCardProps {
  suggestion: AIActionSuggestion;
  onConfirm: () => void;
  onReject: () => void;
  isLoading: boolean;
}

function ActionSuggestionCard({
  suggestion,
  onConfirm,
  onReject,
  isLoading,
}: ActionSuggestionCardProps) {
  const meta = ACTION_METADATA[suggestion.action_type];

  return (
    <div className="p-3 bg-primary/5 border border-primary/20 rounded-lg space-y-2">
      <div className="flex items-start justify-between">
        <div>
          <h4 className="font-medium text-sm">{suggestion.title}</h4>
          <p className="text-xs text-muted-foreground">{suggestion.description}</p>
        </div>
        <Badge variant="outline" className="text-xs">
          {Math.round(suggestion.confidence * 100)}% sicher
        </Badge>
      </div>

      {suggestion.parameters.length > 0 && (
        <div className="text-xs space-y-1">
          {suggestion.parameters.map((param) => (
            <div key={param.name} className="flex justify-between">
              <span className="text-muted-foreground">{param.label}:</span>
              <span>{String(param.value)}</span>
            </div>
          ))}
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        Auswirkung: {suggestion.estimated_impact}
      </p>

      <div className="flex gap-2 pt-1">
        <Button
          size="sm"
          variant="default"
          onClick={onConfirm}
          disabled={isLoading}
          className="flex-1"
        >
          {isLoading ? (
            <Loader2 className="h-3 w-3 animate-spin mr-1" />
          ) : (
            <CheckCircle className="h-3 w-3 mr-1" />
          )}
          Ausführen
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={onReject}
          disabled={isLoading}
          className="flex-1"
        >
          <XCircle className="h-3 w-3 mr-1" />
          Ablehnen
        </Button>
      </div>
    </div>
  );
}

// Quick Action Button
interface QuickActionButtonProps {
  actionType: AIActionType;
  onClick: () => void;
  isLoading: boolean;
  disabled: boolean;
}

function QuickActionButton({
  actionType,
  onClick,
  isLoading,
  disabled,
}: QuickActionButtonProps) {
  const meta = ACTION_METADATA[actionType];

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            onClick={onClick}
            disabled={disabled || isLoading}
            className="h-8 px-2 text-xs"
          >
            {isLoading ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Zap className="h-3 w-3 mr-1" />
            )}
            {meta?.name?.split(' ')[0] || actionType}
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          <p>{meta?.name || actionType}</p>
          <p className="text-xs text-muted-foreground">{meta?.description}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

// ==================== Main Component ====================

export function GlobalAIAssistant() {
  const inputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Local state for pending suggestion
  const [pendingSuggestion, setPendingSuggestion] = useState<AIActionSuggestion | null>(null);

  // Store state
  const {
    view,
    isOpen,
    sessionId: storedSessionId,
    unreadCount,
    pageContext,
    open,
    close,
    toggle,
    setView,
    setSessionId,
    incrementUnread,
    markAsRead,
  } = useAIAssistantStore();

  // Page context detection
  usePageContext();

  // AI Actions - context-aware
  const {
    contextInfo,
    availableActions,
    autonomyLevel,
    pendingSuggestions,
    isExecuting,
    isConfirming,
    executeWithContext,
    confirm,
    lastResult,
  } = useContextAwareAction(
    pageContext.type,
    pageContext.documentId,
    pageContext.entityId
  );

  // Handle suggestion from action result
  useEffect(() => {
    if (lastResult?.status === AIActionStatus.SUGGESTED && lastResult.suggestion) {
      setPendingSuggestion(lastResult.suggestion);
    }
  }, [lastResult]);

  // Chat WebSocket
  const {
    status,
    sessionId,
    error,
    messages,
    isStreaming,
    contextDocuments,
    statusMessage,
    connect,
    sendMessage,
    clearHistory,
  } = useChatWebSocket({
    sessionId: storedSessionId || undefined,
    autoConnect: false,
    onConnected: (sid) => {
      setSessionId(sid);
    },
    onMessage: () => {
      if (!isOpen) {
        incrementUnread();
      }
    },
    onError: (err) => {
      logger.error('AI-Assistent Fehler', err);
    },
  });

  // Get context suggestions
  const suggestions = getContextSuggestions(pageContext);
  const placeholder = getContextPlaceholder(pageContext);

  // ==================== Effects ====================

  // Connect when opened
  useEffect(() => {
    if (isOpen && status === 'disconnected') {
      connect(storedSessionId || undefined);
    }
  }, [isOpen, status, connect, storedSessionId]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (messagesEndRef.current && isOpen) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isStreaming, isOpen]);

  // Focus input when opened
  useEffect(() => {
    if (isOpen && view === 'expanded' && inputRef.current) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen, view]);

  // Keyboard shortcut (Ctrl+K / Cmd+K)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === KEYBOARD_SHORTCUT) {
        e.preventDefault();
        toggle();
      }
      // ESC to close
      if (e.key === 'Escape' && isOpen) {
        close();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [toggle, close, isOpen]);

  // ==================== Handlers ====================

  const handleSend = useCallback(
    (content: string) => {
      if (content.trim() && status === 'connected') {
        sendMessage(content.trim());
      }
    },
    [sendMessage, status]
  );

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      if (inputRef.current) {
        handleSend(inputRef.current.value);
        inputRef.current.value = '';
      }
    },
    [handleSend]
  );

  const handleSuggestionClick = useCallback(
    (suggestion: string) => {
      handleSend(suggestion);
    },
    [handleSend]
  );

  const handleClear = useCallback(() => {
    if (window.confirm('Chat-Verlauf wirklich löschen?')) {
      clearHistory();
    }
  }, [clearHistory]);

  // Action handlers
  const handleQuickAction = useCallback(
    async (actionType: AIActionType) => {
      try {
        const result = await executeWithContext(
          actionType,
          {},
          autonomyLevel === AIActionAutonomyLevel.ADMIN
        );
        // If suggestion returned, it will be handled by the effect
        logger.info('AI Aktion ausgeführt', { actionType, status: result.status });
      } catch (error) {
        logger.error('AI Aktion fehlgeschlagen', error);
      }
    },
    [executeWithContext, autonomyLevel]
  );

  const handleConfirmSuggestion = useCallback(async () => {
    if (!pendingSuggestion) return;
    try {
      await confirm(pendingSuggestion.action_id, true);
      setPendingSuggestion(null);
    } catch (error) {
      logger.error('Bestätigung fehlgeschlagen', error);
    }
  }, [confirm, pendingSuggestion]);

  const handleRejectSuggestion = useCallback(async () => {
    if (!pendingSuggestion) return;
    try {
      await confirm(pendingSuggestion.action_id, false);
      setPendingSuggestion(null);
    } catch (error) {
      logger.error('Ablehnung fehlgeschlagen', error);
    }
  }, [confirm, pendingSuggestion]);

  // Get context-specific quick actions (max 3)
  const quickActions = (contextInfo?.available_actions || []).slice(0, 3);

  // ==================== Render ====================

  return (
    <>
      {/* Floating Button (Minimized State) */}
      <AnimatePresence>
        {!isOpen && (
          <motion.div
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0, opacity: 0 }}
            className="fixed bottom-6 right-6 z-50"
          >
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    onClick={open}
                    size="lg"
                    className={cn(
                      'h-14 w-14 rounded-full shadow-lg hover:shadow-xl transition-all',
                      'bg-primary hover:bg-primary/90'
                    )}
                  >
                    <Bot className="h-6 w-6" />
                    {unreadCount > 0 && (
                      <span className="absolute -top-1 -right-1 h-5 w-5 rounded-full bg-destructive text-destructive-foreground text-xs flex items-center justify-center">
                        {unreadCount}
                      </span>
                    )}
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="left">
                  <p>AI-Assistent öffnen</p>
                  <p className="text-xs text-muted-foreground">Ctrl+K</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Expanded Widget */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className={cn(
              'fixed z-50 bg-background border rounded-lg shadow-2xl overflow-hidden flex flex-col',
              view === 'fullscreen'
                ? 'inset-4'
                : 'bottom-6 right-6'
            )}
            style={
              view !== 'fullscreen'
                ? { width: WIDGET_WIDTH, height: WIDGET_HEIGHT }
                : undefined
            }
          >
            {/* Header */}
            <div className="flex items-center justify-between p-3 border-b bg-muted/30">
              <div className="flex items-center gap-2">
                <div className="p-1.5 rounded-md bg-primary/10">
                  <Sparkles className="h-4 w-4 text-primary" />
                </div>
                <div>
                  <h3 className="font-semibold text-sm">AI-Assistent</h3>
                  <ConnectionStatusIndicator status={status} />
                </div>
              </div>

              <div className="flex items-center gap-1">
                {/* Autonomy Level Badge */}
                <AutonomyLevelBadge level={autonomyLevel} />

                {/* Context Badge */}
                <Badge variant="outline" className="text-xs">
                  {pageContext.type === 'document-detail' && pageContext.documentId
                    ? 'Dokument'
                    : pageContext.type === 'entity-detail' && pageContext.entityId
                    ? 'Kunde/Lieferant'
                    : pageContext.type.replace('-', ' ')}
                </Badge>

                {/* Context Documents */}
                {contextDocuments.length > 0 && (
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Badge variant="secondary" className="text-xs gap-1">
                          <FileText className="h-3 w-3" />
                          {contextDocuments.length}
                        </Badge>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p className="font-medium mb-1">Kontext-Dokumente:</p>
                        {contextDocuments.slice(0, 3).map((doc, i) => (
                          <p key={i} className="text-xs">
                            {doc.filename} ({Math.round(doc.similarity * 100)}%)
                          </p>
                        ))}
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                )}

                {/* Fullscreen Toggle */}
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  onClick={() => setView(view === 'fullscreen' ? 'expanded' : 'fullscreen')}
                >
                  {view === 'fullscreen' ? (
                    <Minimize2 className="h-4 w-4" />
                  ) : (
                    <Maximize2 className="h-4 w-4" />
                  )}
                </Button>

                {/* Close */}
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  onClick={close}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {/* Messages Area */}
            <ScrollArea className="flex-1">
              <div className="p-3 space-y-4">
                {/* Empty State */}
                {messages.length === 0 && status === 'connected' && (
                  <div className="text-center py-8">
                    <Bot className="h-12 w-12 mx-auto text-muted-foreground/50 mb-3" />
                    <p className="text-sm text-muted-foreground mb-4">
                      Wie kann ich dir helfen?
                    </p>

                    {/* Quick Suggestions */}
                    <div className="flex flex-wrap justify-center gap-2">
                      {suggestions.slice(0, 4).map((suggestion, i) => (
                        <QuickSuggestion
                          key={i}
                          suggestion={suggestion}
                          onClick={() => handleSuggestionClick(suggestion)}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {/* Connecting State */}
                {status === 'connecting' && (
                  <div className="flex items-center justify-center py-8 gap-2 text-muted-foreground">
                    <Loader2 className="h-5 w-5 animate-spin" />
                    <span>Verbinde mit AI...</span>
                  </div>
                )}

                {/* Error State */}
                {error && (
                  <div className="p-3 bg-destructive/10 text-destructive rounded-md text-sm">
                    <AlertCircle className="h-4 w-4 inline mr-2" />
                    {error}
                  </div>
                )}

                {/* Messages */}
                {messages
                  .filter((m) => m.role !== 'system')
                  .map((message) => (
                    <ChatMessageComponent
                      key={message.id}
                      message={message}
                      onSourceClick={(docId) => {
                        // Navigate to document
                        window.location.href = `/ablage/${docId}`;
                      }}
                    />
                  ))}

                {/* Status Message */}
                {statusMessage && (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {statusMessage}
                  </div>
                )}

                {/* Pending Action Suggestion (Editor-Level) */}
                {pendingSuggestion && (
                  <ActionSuggestionCard
                    suggestion={pendingSuggestion}
                    onConfirm={handleConfirmSuggestion}
                    onReject={handleRejectSuggestion}
                    isLoading={isConfirming}
                  />
                )}

                {/* Scroll Anchor */}
                <div ref={messagesEndRef} />
              </div>
            </ScrollArea>

            {/* Quick Actions Bar */}
            {quickActions.length > 0 && (
              <div className="px-3 py-2 border-t bg-muted/20 flex items-center gap-2 overflow-x-auto">
                <span className="text-xs text-muted-foreground shrink-0">
                  <Zap className="h-3 w-3 inline mr-1" />
                  Schnellaktionen:
                </span>
                {quickActions.map((actionType) => (
                  <QuickActionButton
                    key={actionType}
                    actionType={actionType}
                    onClick={() => handleQuickAction(actionType)}
                    isLoading={isExecuting}
                    disabled={status !== 'connected'}
                  />
                ))}
              </div>
            )}

            {/* Input Area */}
            <div className="p-3 border-t bg-muted/30">
              <form onSubmit={handleSubmit} className="flex gap-2">
                <Input
                  ref={inputRef}
                  placeholder={placeholder}
                  disabled={status !== 'connected'}
                  className="flex-1"
                />
                <Button
                  type="submit"
                  size="icon"
                  disabled={status !== 'connected' || isStreaming}
                >
                  {isStreaming ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Send className="h-4 w-4" />
                  )}
                </Button>
              </form>

              {/* Keyboard Hint */}
              <div className="flex items-center justify-between mt-2 text-xs text-muted-foreground">
                <span>Ctrl+K zum Öffnen/Schließen</span>
                {messages.length > 0 && (
                  <button
                    onClick={handleClear}
                    className="hover:text-foreground transition-colors"
                  >
                    Verlauf löschen
                  </button>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

export default GlobalAIAssistant;
