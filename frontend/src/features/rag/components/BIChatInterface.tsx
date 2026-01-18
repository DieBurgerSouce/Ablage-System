/**
 * BI-Enhanced Chat Interface Component
 *
 * Chat interface with integrated Business Intelligence capabilities.
 * Automatically detects BI queries and provides structured data visualizations.
 */

import * as React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  MessageSquare,
  Send,
  Loader2,
  BarChart3,
  FileSearch,
  Sparkles,
  ChevronDown,
  Settings2,
  Trash2,
  Bot,
  User,
  Clock,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';
import { BIInsights } from './BIInsights';
import { useBIChat, type BIChatRequest, type BIChatResponse, type BITimeRange } from '../api/bi-api';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  biInsights?: BIChatResponse['bi_insights'];
  sources?: BIChatResponse['sources'];
  isLoading?: boolean;
}

interface BIChatInterfaceProps {
  onSourceClick?: (documentId: string) => void;
  className?: string;
}

export function BIChatInterface({ onSourceClick, className }: BIChatInterfaceProps) {
  const [messages, setMessages] = React.useState<Message[]>([]);
  const [inputValue, setInputValue] = React.useState('');
  const [sessionId, setSessionId] = React.useState<string | undefined>();
  const [enableBI, setEnableBI] = React.useState(true);
  const [timeRange, setTimeRange] = React.useState<BITimeRange>('this_year');
  const [settingsOpen, setSettingsOpen] = React.useState(false);

  const scrollRef = React.useRef<HTMLDivElement>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);

  const { mutate: sendMessage, isPending } = useBIChat();

  // Auto-scroll to bottom
  React.useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Handle send message
  const handleSend = React.useCallback(() => {
    const content = inputValue.trim();
    if (!content || isPending) return;

    // Add user message
    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content,
      timestamp: new Date(),
    };

    // Add loading message
    const loadingMessage: Message = {
      id: `loading-${Date.now()}`,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isLoading: true,
    };

    setMessages((prev) => [...prev, userMessage, loadingMessage]);
    setInputValue('');

    // Send to API
    const request: BIChatRequest = {
      message: content,
      session_id: sessionId,
      enable_bi: enableBI,
      time_range: timeRange,
    };

    sendMessage(request, {
      onSuccess: (response) => {
        setSessionId(response.session_id);

        // Replace loading message with response
        const assistantMessage: Message = {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: response.message,
          timestamp: new Date(),
          biInsights: response.bi_insights,
          sources: response.sources,
        };

        setMessages((prev) =>
          prev.map((m) =>
            m.isLoading ? assistantMessage : m
          )
        );
      },
      onError: (error) => {
        // Replace loading with error message
        const errorMessage: Message = {
          id: `error-${Date.now()}`,
          role: 'assistant',
          content: `Fehler: ${error.message}`,
          timestamp: new Date(),
        };

        setMessages((prev) =>
          prev.map((m) =>
            m.isLoading ? errorMessage : m
          )
        );
      },
    });
  }, [inputValue, isPending, sessionId, enableBI, timeRange, sendMessage]);

  // Handle suggestion click
  const handleSuggestionClick = React.useCallback((suggestion: string) => {
    setInputValue(suggestion);
    inputRef.current?.focus();
  }, []);

  // Handle clear chat
  const handleClear = React.useCallback(() => {
    setMessages([]);
    setSessionId(undefined);
  }, []);

  // Handle key press
  const handleKeyPress = React.useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  // Time range options
  const timeRangeOptions: { value: BITimeRange; label: string }[] = [
    { value: 'last_7_days', label: 'Letzte 7 Tage' },
    { value: 'last_30_days', label: 'Letzte 30 Tage' },
    { value: 'this_month', label: 'Dieser Monat' },
    { value: 'last_quarter', label: 'Letztes Quartal' },
    { value: 'this_quarter', label: 'Dieses Quartal' },
    { value: 'this_year', label: 'Dieses Jahr' },
    { value: 'last_year', label: 'Letztes Jahr' },
    { value: 'all_time', label: 'Alle Zeit' },
  ];

  // Example prompts
  const examplePrompts = [
    'Zeige alle offenen Rechnungen',
    'Wie ist der Umsatz dieses Jahr?',
    'Welche Kunden haben ueberfaellige Rechnungen?',
    'Analysiere die Trend-Entwicklung',
  ];

  return (
    <Card className={cn('flex flex-col h-full', className)}>
      {/* Header */}
      <CardHeader className="flex-none pb-3 border-b">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-primary/10">
              <Sparkles className="h-4 w-4 text-primary" />
            </div>
            <div>
              <CardTitle className="text-base">KI-Geschaeftsassistent</CardTitle>
              <p className="text-xs text-muted-foreground">
                Fragen Sie zu Rechnungen, Kunden, Trends
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              onClick={handleClear}
              disabled={messages.length === 0}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
            <Collapsible open={settingsOpen} onOpenChange={setSettingsOpen}>
              <CollapsibleTrigger asChild>
                <Button variant="ghost" size="icon">
                  <Settings2 className="h-4 w-4" />
                </Button>
              </CollapsibleTrigger>
            </Collapsible>
          </div>
        </div>

        {/* Settings Panel */}
        <Collapsible open={settingsOpen} onOpenChange={setSettingsOpen}>
          <CollapsibleContent className="pt-3">
            <div className="flex flex-wrap items-center gap-4 p-3 bg-muted/50 rounded-lg">
              <div className="flex items-center gap-2">
                <Switch
                  id="enable-bi"
                  checked={enableBI}
                  onCheckedChange={setEnableBI}
                />
                <Label htmlFor="enable-bi" className="text-sm">
                  Business Intelligence aktiviert
                </Label>
              </div>
              <div className="flex items-center gap-2">
                <Label className="text-sm">Zeitraum:</Label>
                <Select value={timeRange} onValueChange={(v) => setTimeRange(v as BITimeRange)}>
                  <SelectTrigger className="w-[160px] h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {timeRangeOptions.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </CollapsibleContent>
        </Collapsible>
      </CardHeader>

      {/* Messages */}
      <ScrollArea className="flex-1 p-4">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center py-8">
            <div className="p-4 rounded-full bg-primary/10 mb-4">
              <MessageSquare className="h-8 w-8 text-primary" />
            </div>
            <h3 className="font-medium mb-2">Stellen Sie eine Frage</h3>
            <p className="text-sm text-muted-foreground mb-4 max-w-sm">
              Ich kann Ihre Geschaeftsdaten analysieren, Trends erkennen und Fragen zu Dokumenten beantworten.
            </p>
            <div className="flex flex-wrap gap-2 justify-center max-w-md">
              {examplePrompts.map((prompt, i) => (
                <Button
                  key={i}
                  variant="outline"
                  size="sm"
                  className="text-xs"
                  onClick={() => handleSuggestionClick(prompt)}
                >
                  {prompt}
                </Button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <AnimatePresence mode="popLayout">
              {messages.map((message) => (
                <motion.div
                  key={message.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className={cn(
                    'flex gap-3',
                    message.role === 'user' ? 'justify-end' : 'justify-start'
                  )}
                >
                  {message.role === 'assistant' && (
                    <div className="flex-none p-2 rounded-full bg-primary/10 h-fit">
                      <Bot className="h-4 w-4 text-primary" />
                    </div>
                  )}

                  <div
                    className={cn(
                      'flex flex-col max-w-[80%]',
                      message.role === 'user' ? 'items-end' : 'items-start'
                    )}
                  >
                    {/* Message Content */}
                    <div
                      className={cn(
                        'rounded-lg px-4 py-2',
                        message.role === 'user'
                          ? 'bg-primary text-primary-foreground'
                          : 'bg-muted'
                      )}
                    >
                      {message.isLoading ? (
                        <div className="flex items-center gap-2">
                          <Loader2 className="h-4 w-4 animate-spin" />
                          <span className="text-sm">Analysiere...</span>
                        </div>
                      ) : (
                        <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                      )}
                    </div>

                    {/* Timestamp */}
                    <div className="flex items-center gap-1 mt-1 text-xs text-muted-foreground">
                      <Clock className="h-3 w-3" />
                      {message.timestamp.toLocaleTimeString('de-DE', {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </div>

                    {/* BI Insights */}
                    {message.biInsights && (
                      <div className="mt-3 w-full">
                        <BIInsights
                          insights={message.biInsights}
                          onSuggestionClick={handleSuggestionClick}
                        />
                      </div>
                    )}

                    {/* Sources */}
                    {message.sources && message.sources.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {message.sources.map((source, i) => (
                          <Badge
                            key={i}
                            variant="outline"
                            className="text-xs cursor-pointer hover:bg-muted"
                            onClick={() => onSourceClick?.(source.document_id)}
                          >
                            <FileSearch className="h-3 w-3 mr-1" />
                            Quelle {i + 1}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>

                  {message.role === 'user' && (
                    <div className="flex-none p-2 rounded-full bg-muted h-fit">
                      <User className="h-4 w-4" />
                    </div>
                  )}
                </motion.div>
              ))}
            </AnimatePresence>
            <div ref={scrollRef} />
          </div>
        )}
      </ScrollArea>

      {/* Input */}
      <div className="flex-none p-4 border-t">
        <div className="flex gap-2">
          <Input
            ref={inputRef}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyPress}
            placeholder="Fragen Sie etwas zu Ihren Geschaeftsdaten..."
            disabled={isPending}
            className="flex-1"
          />
          <Button onClick={handleSend} disabled={!inputValue.trim() || isPending}>
            {isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>

        {/* BI Badge */}
        {enableBI && (
          <div className="flex items-center gap-2 mt-2">
            <Badge variant="secondary" className="text-xs">
              <BarChart3 className="h-3 w-3 mr-1" />
              BI aktiviert
            </Badge>
            <span className="text-xs text-muted-foreground">
              Automatische Datenanalyse fuer Geschaeftsfragen
            </span>
          </div>
        )}
      </div>
    </Card>
  );
}

export default BIChatInterface;
