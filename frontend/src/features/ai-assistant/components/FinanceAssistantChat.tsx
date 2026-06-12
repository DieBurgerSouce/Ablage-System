/**
 * FinanceAssistantChat - Main chat component for the Finance Assistant
 *
 * Vision 2.0 - Phase 1 (Januar 2026)
 *
 * Features:
 * - Natural language chat with context awareness
 * - Action proposals with confirmation
 * - Booking suggestions (SKR03/04)
 * - Proactive insights
 * - Follow-up suggestions
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Loader2, Sparkles, Trash2, Lightbulb, MessageSquare, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { useFinanceAssistant, type ChatMessage } from '../hooks/use-finance-assistant';
import {
  getContextPlaceholder,
  getContextSuggestions,
  usePageContext,
} from '../hooks/use-page-context';
import { ActionProposalCard } from './ActionProposalCard';
import { BookingSuggestionCard } from './BookingSuggestionCard';
import { InsightsList } from './InsightCard';
import {
  INTENT_METADATA,
  AssistantIntent,
  type ExecuteActionResponse,
} from '@/lib/api/services/finance-assistant';

interface FinanceAssistantChatProps {
  className?: string;
  sessionId?: string;
  showInsightsTab?: boolean;
  onClose?: () => void;
}

export function FinanceAssistantChat({
  className,
  sessionId,
  showInsightsTab = true,
  onClose,
}: FinanceAssistantChatProps) {
  const [input, setInput] = useState('');
  const [activeTab, setActiveTab] = useState<'chat' | 'insights'>('chat');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const pageContext = usePageContext();
  const contextSuggestions = getContextSuggestions(pageContext);
  const placeholder = getContextPlaceholder(pageContext);
  const {
    messages,
    sendMessage,
    clearMessages,
    isChatLoading,
    chatError,
    pendingActions,
    pendingBookings,
    dismissAction,
    dismissBooking,
    executeAction,
    rollbackAction,
    insights,
    insightsCount,
    capabilities,
  } = useFinanceAssistant({ sessionId });

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 150)}px`;
    }
  }, [input]);

  const handleSend = useCallback(() => {
    if (!input.trim() || isChatLoading) return;
    sendMessage(input.trim());
    setInput('');
  }, [input, isChatLoading, sendMessage]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSuggestionClick = (suggestion: string) => {
    setInput(suggestion);
    textareaRef.current?.focus();
  };

  return (
    <div className={cn('flex flex-col h-full', className)}>
      {/* Tabs */}
      {showInsightsTab && (
        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'chat' | 'insights')}>
          <TabsList className="w-full grid grid-cols-2">
            <TabsTrigger value="chat" className="flex items-center gap-2">
              <MessageSquare className="h-4 w-4" />
              Chat
            </TabsTrigger>
            <TabsTrigger value="insights" className="flex items-center gap-2">
              <Lightbulb className="h-4 w-4" />
              Insights
              {insightsCount > 0 && (
                <Badge variant="secondary" className="ml-1 h-5 px-1.5">
                  {insightsCount}
                </Badge>
              )}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="chat" className="flex-1 flex flex-col mt-0 data-[state=inactive]:hidden">
            <ChatContent
              messages={messages}
              pendingActions={pendingActions}
              pendingBookings={pendingBookings}
              contextSuggestions={contextSuggestions}
              isChatLoading={isChatLoading}
              chatError={chatError}
              input={input}
              placeholder={placeholder}
              messagesEndRef={messagesEndRef}
              textareaRef={textareaRef}
              onInputChange={setInput}
              onSend={handleSend}
              onKeyDown={handleKeyDown}
              onSuggestionClick={handleSuggestionClick}
              onClearMessages={clearMessages}
              onExecuteAction={executeAction}
              onRollbackAction={rollbackAction}
              onDismissAction={dismissAction}
              onDismissBooking={dismissBooking}
              capabilities={capabilities}
            />
          </TabsContent>

          <TabsContent value="insights" className="flex-1 mt-0 data-[state=inactive]:hidden">
            <ScrollArea className="h-[calc(100%-60px)]">
              <div className="p-4">
                <InsightsList insights={insights} compact={false} />
              </div>
            </ScrollArea>
          </TabsContent>
        </Tabs>
      )}

      {!showInsightsTab && (
        <ChatContent
          messages={messages}
          pendingActions={pendingActions}
          pendingBookings={pendingBookings}
          contextSuggestions={contextSuggestions}
          isChatLoading={isChatLoading}
          chatError={chatError}
          input={input}
          placeholder={placeholder}
          messagesEndRef={messagesEndRef}
          textareaRef={textareaRef}
          onInputChange={setInput}
          onSend={handleSend}
          onKeyDown={handleKeyDown}
          onSuggestionClick={handleSuggestionClick}
          onClearMessages={clearMessages}
          onExecuteAction={executeAction}
          onRollbackAction={rollbackAction}
          onDismissAction={dismissAction}
          onDismissBooking={dismissBooking}
          capabilities={capabilities}
        />
      )}
    </div>
  );
}

// ===== Chat Content Sub-Component =====

interface ChatContentProps {
  messages: ChatMessage[];
  pendingActions: any[];
  pendingBookings: any[];
  contextSuggestions: string[];
  isChatLoading: boolean;
  chatError: Error | null;
  input: string;
  placeholder: string;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
  onSuggestionClick: (suggestion: string) => void;
  onClearMessages: () => void;
  onExecuteAction: (
    actionType: string,
    params: Record<string, unknown>
  ) => Promise<ExecuteActionResponse>;
  onRollbackAction: (actionId: string) => Promise<unknown>;
  onDismissAction: (actionType: string) => void;
  onDismissBooking: (index: number) => void;
  capabilities: { name: string; description: string; examples: string[] }[];
}

function ChatContent({
  messages,
  pendingActions,
  pendingBookings,
  contextSuggestions,
  isChatLoading,
  chatError,
  input,
  placeholder,
  messagesEndRef,
  textareaRef,
  onInputChange,
  onSend,
  onKeyDown,
  onSuggestionClick,
  onClearMessages,
  onExecuteAction,
  onRollbackAction,
  onDismissAction,
  onDismissBooking,
  capabilities,
}: ChatContentProps) {
  const showWelcome = messages.length === 0;

  return (
    <div className="flex flex-col h-full">
      {/* Messages Area */}
      <ScrollArea className="flex-1 p-4">
        {showWelcome ? (
          <WelcomeScreen
            suggestions={contextSuggestions}
            capabilities={capabilities}
            onSuggestionClick={onSuggestionClick}
          />
        ) : (
          <div className="space-y-4">
            {messages.map((message) => (
              <ChatMessageItem key={message.id} message={message} />
            ))}

            {/* Pending Actions */}
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

            {/* Pending Booking Suggestions */}
            <AnimatePresence>
              {pendingBookings.map((booking, index) => (
                <BookingSuggestionCard
                  key={index}
                  suggestion={booking}
                  onDismiss={() => onDismissBooking(index)}
                />
              ))}
            </AnimatePresence>

            <div ref={messagesEndRef} />
          </div>
        )}
      </ScrollArea>

      {/* Error Display */}
      {chatError && (
        <div className="mx-4 mb-2 rounded-lg bg-destructive/10 p-3 flex items-center gap-2 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" />
          {chatError.message}
        </div>
      )}

      {/* Input Area */}
      <div className="border-t p-4">
        <div className="flex items-end gap-2">
          <div className="flex-1 relative">
            <Textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => onInputChange(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder={placeholder}
              className="min-h-[44px] max-h-[150px] resize-none pr-10"
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
                      onClick={onClearMessages}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Chat leeren</TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}
          </div>
          <Button onClick={onSend} disabled={!input.trim() || isChatLoading}>
            {isChatLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>

        {/* Context Suggestions */}
        {showWelcome && contextSuggestions.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {contextSuggestions.slice(0, 3).map((suggestion, index) => (
              <Button
                key={index}
                variant="outline"
                size="sm"
                className="text-xs"
                onClick={() => onSuggestionClick(suggestion)}
              >
                {suggestion}
              </Button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ===== Chat Message Item =====

interface ChatMessageItemProps {
  message: ChatMessage;
}

function ChatMessageItem({ message }: ChatMessageItemProps) {
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
      <div className={cn('flex-1 space-y-1', isUser && 'text-right')}>
        <div
          className={cn(
            'inline-block rounded-lg px-4 py-2 max-w-[85%]',
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

        {/* Intent Badge */}
        {!isUser && intentMeta && !message.isLoading && (
          <div className={cn('flex items-center gap-2', isUser && 'justify-end')}>
            <Badge variant="outline" className="text-xs">
              {intentMeta.label}
            </Badge>
            {message.response?.confidence && (
              <span className="text-xs text-muted-foreground">
                {Math.round(message.response.confidence * 100)}% Konfidenz
              </span>
            )}
          </div>
        )}

        {/* Follow-up Suggestions */}
        {message.response?.follow_up_suggestions && message.response.follow_up_suggestions.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {message.response.follow_up_suggestions.map((suggestion, index) => (
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

// ===== Welcome Screen =====

interface WelcomeScreenProps {
  suggestions: string[];
  capabilities: { name: string; description: string; examples: string[] }[];
  onSuggestionClick: (suggestion: string) => void;
}

function WelcomeScreen({ suggestions, capabilities, onSuggestionClick }: WelcomeScreenProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center p-4">
      <div className="rounded-full bg-primary/10 p-4 mb-4">
        <Sparkles className="h-8 w-8 text-primary" />
      </div>
      <h3 className="text-lg font-semibold mb-2">Finanz-Assistent</h3>
      <p className="text-sm text-muted-foreground mb-6 max-w-sm">
        Ich helfe Ihnen bei der Buchhaltung, Dokumentensuche und Finanzanalyse.
        Stellen Sie mir eine Frage oder wählen Sie einen Vorschlag.
      </p>

      {/* Capability Cards */}
      {capabilities.length > 0 && (
        <div className="grid grid-cols-2 gap-3 mb-6 w-full max-w-md">
          {capabilities.slice(0, 4).map((cap, index) => (
            <button
              key={index}
              className="rounded-lg border p-3 text-left hover:bg-muted/50 transition-colors"
              onClick={() => cap.examples[0] && onSuggestionClick(cap.examples[0])}
            >
              <div className="font-medium text-sm">{cap.name}</div>
              <div className="text-xs text-muted-foreground mt-1">{cap.description}</div>
            </button>
          ))}
        </div>
      )}

      {/* Quick Suggestions */}
      {suggestions.length > 0 && (
        <div className="flex flex-wrap justify-center gap-2">
          {suggestions.slice(0, 4).map((suggestion, index) => (
            <Button
              key={index}
              variant="outline"
              size="sm"
              onClick={() => onSuggestionClick(suggestion)}
            >
              {suggestion}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}
