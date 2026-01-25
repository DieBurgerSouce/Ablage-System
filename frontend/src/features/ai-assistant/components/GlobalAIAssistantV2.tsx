/**
 * Global AI Assistant Widget V2 - Enhanced with Finance Assistant
 *
 * Vision 2.0 - Phase 1 (Januar 2026)
 *
 * Features:
 * - Dual mode: RAG Chat (WebSocket) or Finance Assistant (REST API)
 * - Minimized/Expanded/Fullscreen modes
 * - Context-aware suggestions
 * - Keyboard shortcuts (Ctrl+K)
 * - Action proposals with confirmation
 * - Booking suggestions (SKR03/04)
 * - Proactive insights
 * - Role-based AI actions (Viewer/Editor/Admin)
 * - Conversation history persistence
 * - User feedback on AI responses
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
  Calculator,
  Lightbulb,
  MessageSquare,
  ToggleLeft,
  ToggleRight,
  HelpCircle,
  Trash2,
  History,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
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
import {
  useFinanceAssistant,
  usePersistentConversation,
  ChatMessage,
  ConversationSummary,
} from '../hooks/use-finance-assistant';
import { ConversationHistory } from './ConversationHistory';
import { QuickFeedback, FeedbackDialog } from './FeedbackDialog';
import { useChatWebSocket } from '@/features/rag/hooks/use-chat-websocket';
import { ChatMessage as RAGChatMessage } from '@/features/rag/components/ChatMessage';
import type { ConnectionStatus } from '@/features/rag/types/chat-types';
import { ActionProposalCard } from './ActionProposalCard';
import { BookingSuggestionCard } from './BookingSuggestionCard';
import { InsightCard, InsightsList } from './InsightCard';
import {
  INTENT_METADATA,
  AssistantIntent,
} from '@/lib/api/services/finance-assistant';

// ==================== Constants ====================

const KEYBOARD_SHORTCUT = 'k';
const WIDGET_WIDTH = 480;
const WIDGET_HEIGHT = 640;

// ==================== Types ====================

type AssistantMode = 'rag' | 'finance';

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
      description: 'Mit Bestaetigung',
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

// Mode Toggle
interface ModeToggleProps {
  mode: AssistantMode;
  onChange: (mode: AssistantMode) => void;
}

function ModeToggle({ mode, onChange }: ModeToggleProps) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs gap-1"
            onClick={() => onChange(mode === 'rag' ? 'finance' : 'rag')}
          >
            {mode === 'rag' ? (
              <>
                <FileText className="h-3 w-3" />
                RAG
              </>
            ) : (
              <>
                <Calculator className="h-3 w-3" />
                Finanz
              </>
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          <p>Modus wechseln zu {mode === 'rag' ? 'Finanz-Assistent' : 'RAG Chat'}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

// Finance Chat Message
interface FinanceChatMessageProps {
  message: ChatMessage;
  onDetailedFeedback?: (messageId: string, content: string) => void;
}

function FinanceChatMessage({ message, onDetailedFeedback }: FinanceChatMessageProps) {
  const isUser = message.role === 'user';
  const intent = message.response?.intent as AssistantIntent | undefined;
  const intentMeta = intent ? INTENT_METADATA[intent] : undefined;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn('flex gap-3', isUser && 'flex-row-reverse')}
    >
      {/* Avatar */}
      <div
        className={cn(
          'flex-shrink-0 h-8 w-8 rounded-full flex items-center justify-center',
          isUser ? 'bg-primary text-primary-foreground' : 'bg-muted'
        )}
      >
        {isUser ? (
          <span className="text-sm font-medium">Du</span>
        ) : (
          <Sparkles className="h-4 w-4" />
        )}
      </div>

      {/* Message Content */}
      <div className={cn('flex-1 space-y-1 max-w-[85%]', isUser && 'text-right')}>
        <div
          className={cn(
            'inline-block rounded-lg px-4 py-2',
            isUser ? 'bg-primary text-primary-foreground' : 'bg-muted'
          )}
        >
          {message.isLoading ? (
            <div className="flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span className="text-sm">Denke nach...</span>
            </div>
          ) : (
            <p className="text-sm whitespace-pre-wrap">{message.content}</p>
          )}
        </div>

        {/* Intent Badge + Feedback (for assistant messages) */}
        {!isUser && !message.isLoading && (
          <div className="flex items-center gap-2">
            {intentMeta && (
              <>
                <Badge variant="outline" className="text-xs">
                  {intentMeta.label}
                </Badge>
                {message.response?.confidence && (
                  <span className="text-xs text-muted-foreground">
                    {Math.round(message.response.confidence * 100)}%
                  </span>
                )}
              </>
            )}
            {/* Quick Feedback Buttons */}
            <div className="ml-auto">
              <QuickFeedback
                messageId={message.id}
                onDetailedFeedback={() => onDetailedFeedback?.(message.id, message.content)}
              />
            </div>
          </div>
        )}

        {/* Follow-up Suggestions */}
        {message.response?.follow_up_suggestions &&
          message.response.follow_up_suggestions.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {message.response.follow_up_suggestions.slice(0, 3).map((suggestion, index) => (
                <Badge
                  key={index}
                  variant="secondary"
                  className="cursor-pointer hover:bg-secondary/80 text-xs"
                >
                  {suggestion}
                </Badge>
              ))}
            </div>
          )}

        {/* Timestamp */}
        <div className={cn('text-xs text-muted-foreground', isUser && 'text-right')}>
          {message.timestamp.toLocaleTimeString('de-DE', {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </div>
      </div>
    </motion.div>
  );
}

// ==================== Main Component ====================

export function GlobalAIAssistantV2() {
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Local state
  const [input, setInput] = useState('');
  const [activeTab, setActiveTab] = useState<'chat' | 'insights' | 'history'>('chat');
  const [mode, setMode] = useState<AssistantMode>('finance'); // Default to Finance Assistant
  const [feedbackMessageId, setFeedbackMessageId] = useState<string | null>(null);
  const [feedbackMessageContent, setFeedbackMessageContent] = useState('');

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

  // Persistent conversation for database storage
  const {
    conversation: persistentConversation,
    createConversation,
    updateTitle,
    isCreating: isCreatingConversation,
  } = usePersistentConversation({
    sessionId: storedSessionId || undefined,
    contextPage: pageContext.type,
    autoCreate: mode === 'finance' && isOpen,
  });

  // AI Actions - context-aware
  const { contextInfo, autonomyLevel } = useContextAwareAction(
    pageContext.type,
    pageContext.documentId,
    pageContext.entityId
  );

  // Finance Assistant
  const {
    messages: financeMessages,
    sendMessage: sendFinanceMessage,
    clearMessages: clearFinanceMessages,
    isChatLoading: isFinanceLoading,
    chatError: financeError,
    pendingActions,
    pendingBookings,
    dismissAction,
    dismissBooking,
    executeAction,
    rollbackAction,
    insights,
    insightsCount,
    capabilities,
  } = useFinanceAssistant({ sessionId: storedSessionId || undefined });

  // Handlers for conversation history
  const handleSelectConversation = useCallback((conv: ConversationSummary) => {
    setSessionId(conv.session_id);
    setActiveTab('chat');
    // Clear current messages and load from selected conversation
    clearFinanceMessages();
  }, [setSessionId, clearFinanceMessages]);

  const handleNewConversation = useCallback(() => {
    // Generate new session ID
    const newSessionId = crypto.randomUUID();
    setSessionId(newSessionId);
    clearFinanceMessages();
    setActiveTab('chat');
  }, [setSessionId, clearFinanceMessages]);

  // RAG Chat WebSocket
  const {
    status: ragStatus,
    sessionId,
    error: ragError,
    messages: ragMessages,
    isStreaming,
    contextDocuments,
    statusMessage,
    connect: ragConnect,
    sendMessage: sendRagMessage,
    clearHistory: clearRagHistory,
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

  // Connect RAG when opened in RAG mode
  useEffect(() => {
    if (isOpen && mode === 'rag' && ragStatus === 'disconnected') {
      ragConnect(storedSessionId || undefined);
    }
  }, [isOpen, mode, ragStatus, ragConnect, storedSessionId]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (messagesEndRef.current && isOpen) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [financeMessages, ragMessages, isStreaming, isOpen]);

  // Focus input when opened
  useEffect(() => {
    if (isOpen && view === 'expanded' && inputRef.current) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen, view]);

  // Auto-resize textarea
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 120)}px`;
    }
  }, [input]);

  // Keyboard shortcut (Ctrl+K / Cmd+K)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === KEYBOARD_SHORTCUT) {
        e.preventDefault();
        toggle();
      }
      if (e.key === 'Escape' && isOpen) {
        close();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [toggle, close, isOpen]);

  // ==================== Handlers ====================

  const handleSend = useCallback(() => {
    if (!input.trim()) return;

    if (mode === 'finance') {
      sendFinanceMessage(input.trim());
    } else {
      if (ragStatus === 'connected') {
        sendRagMessage(input.trim());
      }
    }
    setInput('');
  }, [input, mode, sendFinanceMessage, sendRagMessage, ragStatus]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSuggestionClick = useCallback((suggestion: string) => {
    setInput(suggestion);
    inputRef.current?.focus();
  }, []);

  const handleClear = useCallback(() => {
    if (mode === 'finance') {
      clearFinanceMessages();
    } else {
      clearRagHistory();
    }
  }, [mode, clearFinanceMessages, clearRagHistory]);

  // Feedback handlers
  const handleOpenFeedback = useCallback((messageId: string, content: string) => {
    setFeedbackMessageId(messageId);
    setFeedbackMessageContent(content);
  }, []);

  const handleCloseFeedback = useCallback(() => {
    setFeedbackMessageId(null);
    setFeedbackMessageContent('');
  }, []);

  const messages = mode === 'finance' ? financeMessages : ragMessages;
  const isLoading = mode === 'finance' ? isFinanceLoading : isStreaming;
  const error = mode === 'finance' ? financeError?.message : ragError;
  const isConnected = mode === 'finance' ? true : ragStatus === 'connected';
  const showEmpty = messages.length === 0;

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
                    {insightsCount > 0 && (
                      <span className="absolute -bottom-1 -right-1 h-5 w-5 rounded-full bg-yellow-500 text-white text-xs flex items-center justify-center">
                        <Lightbulb className="h-3 w-3" />
                      </span>
                    )}
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="left">
                  <p>AI-Assistent oeffnen</p>
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
              view === 'fullscreen' ? 'inset-4' : 'bottom-6 right-6'
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
                  <h3 className="font-semibold text-sm">
                    {mode === 'finance' ? 'Finanz-Assistent' : 'RAG Chat'}
                  </h3>
                  {mode === 'rag' ? (
                    <ConnectionStatusIndicator status={ragStatus} />
                  ) : (
                    <span className="text-xs text-green-500">Bereit</span>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-1">
                <ModeToggle mode={mode} onChange={setMode} />
                <AutonomyLevelBadge level={autonomyLevel} />

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

                <Button variant="ghost" size="icon" className="h-7 w-7" onClick={close}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {/* Tabs (only in Finance mode) */}
            {mode === 'finance' && (
              <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'chat' | 'insights' | 'history')}>
                <TabsList className="w-full grid grid-cols-3 rounded-none border-b">
                  <TabsTrigger value="chat" className="text-xs">
                    <MessageSquare className="h-3 w-3 mr-1" />
                    Chat
                  </TabsTrigger>
                  <TabsTrigger value="insights" className="text-xs">
                    <Lightbulb className="h-3 w-3 mr-1" />
                    Insights
                    {insightsCount > 0 && (
                      <Badge variant="secondary" className="ml-1 h-4 px-1 text-[10px]">
                        {insightsCount}
                      </Badge>
                    )}
                  </TabsTrigger>
                  <TabsTrigger value="history" className="text-xs">
                    <History className="h-3 w-3 mr-1" />
                    Verlauf
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="chat" className="flex-1 flex flex-col mt-0">
                  <ChatArea
                    mode={mode}
                    messages={financeMessages}
                    ragMessages={[]}
                    pendingActions={pendingActions}
                    pendingBookings={pendingBookings}
                    suggestions={suggestions}
                    showEmpty={showEmpty}
                    isLoading={isLoading}
                    error={error}
                    capabilities={capabilities}
                    messagesEndRef={messagesEndRef}
                    onSuggestionClick={handleSuggestionClick}
                    onExecuteAction={executeAction}
                    onRollbackAction={rollbackAction}
                    onDismissAction={dismissAction}
                    onDismissBooking={dismissBooking}
                    onDetailedFeedback={handleOpenFeedback}
                  />
                </TabsContent>

                <TabsContent value="insights" className="flex-1 mt-0">
                  <ScrollArea className="h-full">
                    <div className="p-4">
                      <InsightsList insights={insights} compact={false} />
                    </div>
                  </ScrollArea>
                </TabsContent>

                <TabsContent value="history" className="flex-1 mt-0">
                  <ConversationHistory
                    onSelectConversation={handleSelectConversation}
                    onNewConversation={handleNewConversation}
                    selectedConversationId={persistentConversation?.id}
                    compact={view !== 'fullscreen'}
                  />
                </TabsContent>
              </Tabs>
            )}

            {/* RAG Mode Content */}
            {mode === 'rag' && (
              <ChatArea
                mode={mode}
                messages={[]}
                ragMessages={ragMessages}
                pendingActions={[]}
                pendingBookings={[]}
                suggestions={suggestions}
                showEmpty={ragMessages.length === 0 && ragStatus === 'connected'}
                isLoading={isStreaming}
                error={ragError}
                capabilities={[]}
                messagesEndRef={messagesEndRef}
                statusMessage={statusMessage}
                contextDocuments={contextDocuments}
                onSuggestionClick={handleSuggestionClick}
                onExecuteAction={async () => ({ action_id: '', status: 'completed', success: true, message: '', affected_count: 0, rollback_possible: false, execution_time_ms: 0, metadata: {} })}
                onRollbackAction={async () => {}}
                onDismissAction={() => {}}
                onDismissBooking={() => {}}
                onDetailedFeedback={handleOpenFeedback}
              />
            )}

            {/* Input Area */}
            <div className="p-3 border-t bg-muted/30">
              <div className="flex gap-2">
                <div className="flex-1 relative">
                  <Textarea
                    ref={inputRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={placeholder}
                    disabled={!isConnected || isLoading}
                    className="min-h-[44px] max-h-[120px] resize-none pr-10"
                    rows={1}
                  />
                  {messages.length > 0 && (
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="absolute right-2 top-1/2 -translate-y-1/2 h-7 w-7"
                            onClick={handleClear}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Chat leeren</TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  )}
                </div>
                <Button onClick={handleSend} disabled={!input.trim() || !isConnected || isLoading}>
                  {isLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Send className="h-4 w-4" />
                  )}
                </Button>
              </div>
              <div className="mt-2 text-xs text-muted-foreground text-center">
                Ctrl+K zum Oeffnen/Schliessen • Shift+Enter fuer neue Zeile
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Feedback Dialog */}
      <FeedbackDialog
        messageId={feedbackMessageId || ''}
        messageContent={feedbackMessageContent}
        open={!!feedbackMessageId}
        onOpenChange={(open) => {
          if (!open) handleCloseFeedback();
        }}
        onSuccess={() => {
          handleCloseFeedback();
        }}
      />
    </>
  );
}

// ==================== Chat Area Sub-Component ====================

interface ChatAreaProps {
  mode: AssistantMode;
  messages: ChatMessage[];
  ragMessages: any[];
  pendingActions: any[];
  pendingBookings: any[];
  suggestions: string[];
  showEmpty: boolean;
  isLoading: boolean;
  error?: string | null;
  capabilities: { name: string; description: string; examples: string[] }[];
  messagesEndRef: React.RefObject<HTMLDivElement>;
  statusMessage?: string;
  contextDocuments?: any[];
  onSuggestionClick: (suggestion: string) => void;
  onExecuteAction: (actionType: string, params: Record<string, unknown>) => Promise<any>;
  onRollbackAction: (actionId: string) => Promise<void>;
  onDismissAction: (actionType: string) => void;
  onDismissBooking: (index: number) => void;
  onDetailedFeedback?: (messageId: string, content: string) => void;
}

function ChatArea({
  mode,
  messages,
  ragMessages,
  pendingActions,
  pendingBookings,
  suggestions,
  showEmpty,
  isLoading,
  error,
  capabilities,
  messagesEndRef,
  statusMessage,
  contextDocuments,
  onSuggestionClick,
  onExecuteAction,
  onRollbackAction,
  onDismissAction,
  onDismissBooking,
  onDetailedFeedback,
}: ChatAreaProps) {
  return (
    <ScrollArea className="flex-1">
      <div className="p-3 space-y-4">
        {/* Empty State */}
        {showEmpty && (
          <div className="text-center py-8">
            <Bot className="h-12 w-12 mx-auto text-muted-foreground/50 mb-3" />
            <p className="text-sm text-muted-foreground mb-4">
              {mode === 'finance'
                ? 'Ich bin Ihr Finanz-Assistent. Wie kann ich helfen?'
                : 'Wie kann ich dir helfen?'}
            </p>

            {/* Capability Cards (Finance mode) */}
            {mode === 'finance' && capabilities.length > 0 && (
              <div className="grid grid-cols-2 gap-2 mb-4 px-4">
                {capabilities.slice(0, 4).map((cap, index) => (
                  <button
                    key={index}
                    className="rounded-lg border p-2 text-left hover:bg-muted/50 transition-colors"
                    onClick={() => cap.examples[0] && onSuggestionClick(cap.examples[0])}
                  >
                    <div className="font-medium text-xs">{cap.name}</div>
                    <div className="text-[10px] text-muted-foreground mt-0.5 line-clamp-2">
                      {cap.description}
                    </div>
                  </button>
                ))}
              </div>
            )}

            {/* Quick Suggestions */}
            <div className="flex flex-wrap justify-center gap-2">
              {suggestions.slice(0, 4).map((suggestion, i) => (
                <QuickSuggestion
                  key={i}
                  suggestion={suggestion}
                  onClick={() => onSuggestionClick(suggestion)}
                />
              ))}
            </div>
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="p-3 bg-destructive/10 text-destructive rounded-md text-sm">
            <AlertCircle className="h-4 w-4 inline mr-2" />
            {error}
          </div>
        )}

        {/* Finance Messages */}
        {mode === 'finance' &&
          messages.map((message) => (
            <FinanceChatMessage
              key={message.id}
              message={message}
              onDetailedFeedback={onDetailedFeedback}
            />
          ))}

        {/* RAG Messages */}
        {mode === 'rag' &&
          ragMessages
            .filter((m) => m.role !== 'system')
            .map((message) => (
              <RAGChatMessage
                key={message.id}
                message={message}
                onSourceClick={(docId) => {
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

        {/* Pending Actions (Finance mode) */}
        {mode === 'finance' && (
          <AnimatePresence>
            {pendingActions.map((action) => (
              <ActionProposalCard
                key={action.action_type}
                action={action}
                onExecute={async (a) => onExecuteAction(a.action_type, a.parameters)}
                onDismiss={() => onDismissAction(action.action_type)}
                onRollback={onRollbackAction}
              />
            ))}
          </AnimatePresence>
        )}

        {/* Pending Booking Suggestions (Finance mode) */}
        {mode === 'finance' && (
          <AnimatePresence>
            {pendingBookings.map((booking, index) => (
              <BookingSuggestionCard
                key={index}
                suggestion={booking}
                onDismiss={() => onDismissBooking(index)}
              />
            ))}
          </AnimatePresence>
        )}

        {/* Scroll Anchor */}
        <div ref={messagesEndRef} />
      </div>
    </ScrollArea>
  );
}

export default GlobalAIAssistantV2;
