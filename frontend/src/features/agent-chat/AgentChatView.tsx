/**
 * AgentChatView - KI-Assistent Chat-Seite mit Chain-of-Thought UI
 *
 * Vollseitige Chat-Ansicht fuer den Financial Orchestrator.
 * Das KRITISCHE Alleinstellungsmerkmal: Sichtbare Chain-of-Thought-Anzeige
 * mit ausklappbaren Denkschritten, die zeigen, welche Sub-Agents aufgerufen wurden.
 */

import { useState, useRef, useEffect, useCallback, type KeyboardEvent } from 'react';
import { logger } from '@/lib/logger';
import { useMutation } from '@tanstack/react-query';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { apiClient } from '@/lib/api/client';
import {
  Bot,
  Send,
  Loader2,
  ChevronDown,
  ChevronRight,
  FileText,
  DollarSign,
  Shield,
  Link,
  AlertTriangle,
  Brain,
  CheckCircle2,
  XCircle,
  Clock,
  SkipForward,
  Activity,
  Sparkles,
  AlertCircle,
} from 'lucide-react';

// ============================================================================
// TYPEN
// ============================================================================

interface ThinkingStep {
  id: string;
  agent_type: string;
  agent_name: string;
  description: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
  details: string[];
  result_summary: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  error: string | null;
}

interface SuggestedAction {
  label: string;
  action_type: string;
  params: Record<string, unknown>;
  variant: 'default' | 'outline' | 'ghost' | 'destructive';
}

interface AgentQueryResponse {
  answer: string;
  thinking_steps: ThinkingStep[];
  suggested_actions: SuggestedAction[];
  conversation_id: string | null;
  total_duration_ms: number;
  model_used: string | null;
}

interface AgentQueryRequest {
  query: string;
  conversation_id: string | null;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  response?: AgentQueryResponse;
  timestamp: Date;
}

// ============================================================================
// HILFSFUNKTIONEN
// ============================================================================

function getAgentIcon(agentType: string): React.ReactNode {
  const iconClass = 'h-4 w-4';
  switch (agentType.toLowerCase()) {
    case 'document':
      return <FileText className={iconClass} />;
    case 'finance':
    case 'financial':
      return <DollarSign className={iconClass} />;
    case 'compliance':
      return <Shield className={iconClass} />;
    case 'matching':
      return <Link className={iconClass} />;
    case 'anomaly':
      return <AlertTriangle className={iconClass} />;
    default:
      return <Brain className={iconClass} />;
  }
}

function getStatusIcon(status: ThinkingStep['status']): React.ReactNode {
  switch (status) {
    case 'completed':
      return <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />;
    case 'failed':
      return <XCircle className="h-4 w-4 text-destructive shrink-0" />;
    case 'running':
      return <Loader2 className="h-4 w-4 text-blue-500 animate-spin shrink-0" />;
    case 'skipped':
      return <SkipForward className="h-4 w-4 text-muted-foreground shrink-0" />;
    default:
      return <Clock className="h-4 w-4 text-muted-foreground shrink-0" />;
  }
}

function formatDuration(ms: number | null): string {
  if (ms === null) return '';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString('de-DE', {
    hour: '2-digit',
    minute: '2-digit',
  });
}

// ============================================================================
// DENKSCHRITTE-KOMPONENTE (Chain of Thought)
// ============================================================================

interface ThinkingStepItemProps {
  step: ThinkingStep;
  isLast: boolean;
  index: number;
}

function ThinkingStepItem({ step, isLast, index }: ThinkingStepItemProps) {
  const [detailsOpen, setDetailsOpen] = useState(false);

  return (
    <div
      className={cn(
        'flex gap-3 animate-in fade-in slide-in-from-bottom-2',
      )}
      style={{ animationDelay: `${index * 80}ms`, animationFillMode: 'both' }}
    >
      {/* Timeline-Linie */}
      <div className="flex flex-col items-center">
        <div
          className={cn(
            'flex items-center justify-center w-7 h-7 rounded-full shrink-0 border',
            step.status === 'completed' && 'bg-green-50 border-green-200 text-green-700',
            step.status === 'failed' && 'bg-red-50 border-red-200 text-destructive',
            step.status === 'running' && 'bg-blue-50 border-blue-200 text-blue-700',
            step.status === 'skipped' && 'bg-muted border-muted-foreground/20 text-muted-foreground',
            step.status === 'pending' && 'bg-muted border-border text-muted-foreground',
          )}
        >
          {getAgentIcon(step.agent_type)}
        </div>
        {!isLast && (
          <div className="w-px flex-1 bg-border mt-1 min-h-[12px]" />
        )}
      </div>

      {/* Schritt-Inhalt */}
      <div className="flex-1 pb-3">
        <div className="flex items-start gap-2 flex-wrap">
          <div className="flex items-center gap-1.5">
            {getStatusIcon(step.status)}
            <span className="text-sm font-medium">{step.agent_name}</span>
          </div>
          {step.duration_ms !== null && (
            <Badge variant="outline" className="text-[10px] h-4 px-1.5">
              {formatDuration(step.duration_ms)}
            </Badge>
          )}
        </div>

        <p className="text-xs text-muted-foreground mt-0.5">{step.description}</p>

        {step.result_summary && (
          <p className="text-xs text-foreground/80 mt-1 italic">
            {step.result_summary}
          </p>
        )}

        {step.error && (
          <p className="text-xs text-destructive mt-1 flex items-center gap-1">
            <AlertCircle className="h-3 w-3 shrink-0" />
            {step.error}
          </p>
        )}

        {/* Ausklappbare Details */}
        {step.details && step.details.length > 0 && (
          <Collapsible open={detailsOpen} onOpenChange={setDetailsOpen}>
            <CollapsibleTrigger asChild>
              <button className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground mt-1 transition-colors">
                {detailsOpen ? (
                  <ChevronDown className="h-3 w-3" />
                ) : (
                  <ChevronRight className="h-3 w-3" />
                )}
                {step.details.length} Detail{step.details.length !== 1 ? 's' : ''}
              </button>
            </CollapsibleTrigger>
            <CollapsibleContent className="animate-in fade-in slide-in-from-top-1">
              <ul className="mt-1.5 space-y-0.5 ml-3 border-l pl-3 border-border">
                {step.details.map((detail, i) => (
                  <li key={i} className="text-[11px] text-muted-foreground">
                    {detail}
                  </li>
                ))}
              </ul>
            </CollapsibleContent>
          </Collapsible>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// CHAIN-OF-THOUGHT-SEKTION
// ============================================================================

interface ChainOfThoughtSectionProps {
  steps: ThinkingStep[];
  totalDurationMs: number;
}

function ChainOfThoughtSection({ steps, totalDurationMs }: ChainOfThoughtSectionProps) {
  const [open, setOpen] = useState(false);

  const completedCount = steps.filter((s) => s.status === 'completed').length;
  const hasFailures = steps.some((s) => s.status === 'failed');

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <button
          className={cn(
            'flex items-center gap-2 text-xs px-3 py-1.5 rounded-md w-full text-left',
            'hover:bg-muted/60 transition-colors border border-border/50',
            hasFailures && 'border-red-200',
          )}
        >
          {open ? (
            <ChevronDown className="h-3.5 w-3.5 shrink-0" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 shrink-0" />
          )}
          <Activity className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          <span className="font-medium">
            {open ? 'Denkschritte verbergen' : 'Denkschritte anzeigen'}
          </span>
          <span className="text-muted-foreground ml-auto flex items-center gap-2">
            <span>
              {steps.length} Schritt{steps.length !== 1 ? 'e' : ''}
              {completedCount < steps.length && `, ${completedCount} abgeschlossen`}
            </span>
            <Badge variant="outline" className="text-[10px] h-4 px-1.5">
              {formatDuration(totalDurationMs)}
            </Badge>
          </span>
        </button>
      </CollapsibleTrigger>

      <CollapsibleContent className="animate-in fade-in slide-in-from-top-2">
        <div className="mt-2 pl-2 pr-1">
          {steps.map((step, index) => (
            <ThinkingStepItem
              key={step.id}
              step={step}
              isLast={index === steps.length - 1}
              index={index}
            />
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

// ============================================================================
// ASSISTENT-NACHRICHT
// ============================================================================

interface AssistantMessageProps {
  message: ChatMessage;
}

function AssistantMessageBubble({ message }: AssistantMessageProps) {
  const response = message.response;

  return (
    <div className="flex gap-3 justify-start animate-in fade-in slide-in-from-bottom-3">
      <div className="flex flex-col items-center shrink-0">
        <div className="w-8 h-8 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center">
          <Bot className="h-4 w-4 text-primary" />
        </div>
      </div>

      <div className="flex flex-col gap-2 max-w-[85%]">
        {/* Antworttext */}
        <div className="bg-muted rounded-lg px-4 py-3">
          <div className="text-sm whitespace-pre-wrap break-words">{message.content}</div>
          <div className="text-[10px] text-muted-foreground mt-1.5 flex items-center gap-2">
            <span>{formatTime(message.timestamp)}</span>
            {response?.model_used && (
              <>
                <span>·</span>
                <span>{response.model_used}</span>
              </>
            )}
          </div>
        </div>

        {/* Chain-of-Thought-Sektion */}
        {response && response.thinking_steps.length > 0 && (
          <ChainOfThoughtSection
            steps={response.thinking_steps}
            totalDurationMs={response.total_duration_ms}
          />
        )}

        {/* Vorgeschlagene Aktionen */}
        {response && response.suggested_actions.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-[10px] text-muted-foreground font-medium uppercase tracking-wide">
              Vorgeschlagene Aktionen
            </p>
            <div className="flex flex-wrap gap-2">
              {response.suggested_actions.map((action, index) => (
                <Button
                  key={index}
                  variant={action.variant}
                  size="sm"
                  className="h-7 text-xs"
                  onClick={() => {
                    // Aktion-Handler: Params koennen fuer Navigation oder API-Aufrufe genutzt werden
                    logger.debug('Aktion ausgefuehrt:', action.action_type, action.params);
                  }}
                >
                  {action.label}
                </Button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// BENUTZER-NACHRICHT
// ============================================================================

interface UserMessageProps {
  message: ChatMessage;
}

function UserMessageBubble({ message }: UserMessageProps) {
  return (
    <div className="flex gap-3 justify-end animate-in fade-in slide-in-from-bottom-3">
      <div className="max-w-[80%] bg-primary text-primary-foreground rounded-lg px-4 py-3">
        <div className="text-sm whitespace-pre-wrap break-words">{message.content}</div>
        <div className="text-[10px] text-primary-foreground/60 mt-1.5">
          {formatTime(message.timestamp)}
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// EINGABEFELD
// ============================================================================

interface AgentChatInputProps {
  onSend: (message: string) => void;
  isLoading: boolean;
}

function AgentChatInput({ onSend, isLoading }: AgentChatInputProps) {
  const [value, setValue] = useState('');

  const handleSend = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setValue('');
  }, [value, isLoading, onSend]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  return (
    <div className="border-t bg-background px-4 py-3">
      <div className="flex gap-2 items-end">
        <Textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Stellen Sie Ihre Frage..."
          className="min-h-[44px] max-h-40 resize-none text-sm"
          disabled={isLoading}
          rows={1}
        />
        <Button
          size="icon"
          onClick={handleSend}
          disabled={!value.trim() || isLoading}
          className="shrink-0 h-11 w-11"
        >
          {isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </Button>
      </div>
      <p className="text-[10px] text-muted-foreground text-center mt-1.5">
        Shift+Enter fuer Zeilenumbruch
      </p>
    </div>
  );
}

// ============================================================================
// HAUPTKOMPONENTE
// ============================================================================

export function AgentChatView() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [statusOk, setStatusOk] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Automatisch zum Ende scrollen bei neuen Nachrichten
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // API-Mutation fuer Agent-Anfragen
  const mutation = useMutation({
    mutationFn: async (query: string): Promise<AgentQueryResponse> => {
      const payload: AgentQueryRequest = {
        query,
        conversation_id: conversationId,
      };
      const response = await apiClient.post<AgentQueryResponse>('/agent/query', payload);
      return response.data;
    },
    onSuccess: (data, query) => {
      // conversation_id beibehalten fuer Folgeanfragen
      if (data.conversation_id) {
        setConversationId(data.conversation_id);
      }

      // Assistenten-Nachricht hinzufuegen
      const assistantMessage: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: data.answer,
        response: data,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
      setStatusOk(true);
    },
    onError: () => {
      // Fehlernachricht als Assistent-Antwort hinzufuegen
      const errorMessage: ChatMessage = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content:
          'Es ist ein Fehler aufgetreten. Bitte versuchen Sie es erneut oder kontaktieren Sie den Support.',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
      setStatusOk(false);
    },
  });

  const handleSend = useCallback(
    (query: string) => {
      // Benutzernachricht sofort hinzufuegen
      const userMessage: ChatMessage = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: query,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMessage]);

      // Anfrage senden
      mutation.mutate(query);
    },
    [mutation]
  );

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header */}
      <div className="border-b px-6 py-4 bg-background shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center">
              <Sparkles className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h1 className="text-lg font-semibold leading-none">KI-Assistent</h1>
              <p className="text-xs text-muted-foreground mt-0.5">
                Financial Orchestrator mit Chain-of-Thought
              </p>
            </div>
          </div>

          {/* Status-Indikator */}
          <div className="flex items-center gap-2">
            <div
              className={cn(
                'w-2 h-2 rounded-full',
                statusOk ? 'bg-green-500 animate-pulse' : 'bg-yellow-500'
              )}
            />
            <span className="text-xs text-muted-foreground">
              {statusOk ? 'Betriebsbereit' : 'Eingeschraenkt'}
            </span>
          </div>
        </div>
      </div>

      {/* Nachrichten-Bereich */}
      <ScrollArea className="flex-1 min-h-0" ref={scrollRef}>
        <div className="px-6 py-4 space-y-4 max-w-4xl mx-auto">
          {/* Leer-Zustand */}
          {messages.length === 0 && !mutation.isPending && (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="w-16 h-16 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center mb-4">
                <Bot className="h-8 w-8 text-primary" />
              </div>
              <h2 className="text-base font-medium mb-2">Willkommen beim KI-Assistenten</h2>
              <p className="text-sm text-muted-foreground max-w-sm">
                Stellen Sie Fragen zu Ihren Finanzdokumenten, Rechnungen oder
                Zahlungen. Der Assistent zeigt transparent, welche Analyse-Schritte
                durchgefuehrt werden.
              </p>

              {/* Beispielfragen */}
              <div className="mt-6 flex flex-wrap gap-2 justify-center max-w-lg">
                {[
                  'Welche Rechnungen sind ueberfaellig?',
                  'Zeige offene Zahlungen',
                  'Analysiere den Cashflow',
                  'Suche nach Duplikaten',
                ].map((example) => (
                  <button
                    key={example}
                    onClick={() => handleSend(example)}
                    className="text-xs border rounded-full px-3 py-1.5 hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                  >
                    {example}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Nachrichten-Liste */}
          {messages.map((message) =>
            message.role === 'user' ? (
              <UserMessageBubble key={message.id} message={message} />
            ) : (
              <AssistantMessageBubble key={message.id} message={message} />
            )
          )}

          {/* Lade-Indikator */}
          {mutation.isPending && (
            <div className="flex gap-3 justify-start animate-in fade-in">
              <div className="w-8 h-8 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center shrink-0">
                <Bot className="h-4 w-4 text-primary" />
              </div>
              <div className="bg-muted rounded-lg px-4 py-3">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>Wird verarbeitet...</span>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </ScrollArea>

      {/* Eingabefeld */}
      <div className="shrink-0 max-w-4xl w-full mx-auto px-6">
        <AgentChatInput onSend={handleSend} isLoading={mutation.isPending} />
      </div>
    </div>
  );
}
