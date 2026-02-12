/**
 * Portal Messages Route
 *
 * Kundenportal Nachrichten/Chat.
 */

import { createFileRoute } from '@tanstack/react-router';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';
import {
  Send,
  MessageSquare,
  Mail,
  MailOpen,
  User,
  Building,
  Loader2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  usePortalMessages,
  usePortalSendMessage,
  usePortalMarkMessageRead,
  usePortalUnreadCount,
} from '@/features/portal';
import type { PortalMessage } from '@/features/portal';

const messageSchema = z.object({
  subject: z.string().min(3, 'Betreff muss mindestens 3 Zeichen haben'),
  content: z.string().min(10, 'Nachricht muss mindestens 10 Zeichen haben'),
});

type MessageFormData = z.infer<typeof messageSchema>;

export const Route = createFileRoute('/portal/messages')({
  component: MessagesPage,
});

function MessagesPage() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedMessage, setSelectedMessage] = useState<PortalMessage | null>(null);
  const { data: messages, isLoading } = usePortalMessages({});
  const { data: unreadCount } = usePortalUnreadCount();
  const sendMessage = usePortalSendMessage();
  const markRead = usePortalMarkMessageRead();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<MessageFormData>({
    resolver: zodResolver(messageSchema),
  });

  const onSubmit = async (data: MessageFormData) => {
    try {
      await sendMessage.mutateAsync({
        subject: data.subject,
        content: data.content,
      });
      setDialogOpen(false);
      reset();
    } catch {
      // Error handled by mutation
    }
  };

  const handleMessageClick = async (message: PortalMessage) => {
    setSelectedMessage(message);
    if (!message.is_read && message.direction === 'inbound') {
      await markRead.mutateAsync(message.id);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Nachrichten</h1>
          <p className="text-muted-foreground mt-1">
            Kommunikation mit unserem Team
            {unreadCount?.unread_count ? (
              <Badge variant="secondary" className="ml-2">
                {unreadCount.unread_count} ungelesen
              </Badge>
            ) : null}
          </p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Send className="mr-2 h-4 w-4" />
              Neue Nachricht
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-[500px]">
            <DialogHeader>
              <DialogTitle>Neue Nachricht senden</DialogTitle>
              <DialogDescription>
                Senden Sie uns eine Nachricht. Wir antworten schnellstmöglich.
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleSubmit(onSubmit)}>
              <div className="space-y-4 py-4">
                <div className="space-y-2">
                  <Label htmlFor="subject">Betreff *</Label>
                  <Input
                    id="subject"
                    placeholder="Worum geht es?"
                    {...register('subject')}
                  />
                  {errors.subject && (
                    <p className="text-sm text-destructive">{errors.subject.message}</p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="content">Nachricht *</Label>
                  <Textarea
                    id="content"
                    placeholder="Ihre Nachricht..."
                    rows={6}
                    {...register('content')}
                  />
                  {errors.content && (
                    <p className="text-sm text-destructive">{errors.content.message}</p>
                  )}
                </div>
              </div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>
                  Abbrechen
                </Button>
                <Button type="submit" disabled={isSubmitting}>
                  {isSubmitting ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Wird gesendet...
                    </>
                  ) : (
                    <>
                      <Send className="mr-2 h-4 w-4" />
                      Senden
                    </>
                  )}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Messages Grid */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Messages List */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="text-lg">Posteingang</CardTitle>
            <CardDescription>
              {messages?.total ?? 0} Nachrichten
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="space-y-0 divide-y">
                {[...Array(3)].map((_, i) => (
                  <div key={i} className="p-4">
                    <Skeleton className="h-16 w-full" />
                  </div>
                ))}
              </div>
            ) : messages?.items && messages.items.length > 0 ? (
              <div className="divide-y max-h-[600px] overflow-y-auto">
                {messages.items.map((message) => (
                  <button
                    key={message.id}
                    onClick={() => handleMessageClick(message)}
                    className={cn(
                      'w-full text-left p-4 hover:bg-muted/50 transition-colors',
                      selectedMessage?.id === message.id && 'bg-muted',
                      !message.is_read && message.direction === 'inbound' && 'bg-primary/5'
                    )}
                  >
                    <div className="flex items-start gap-3">
                      <div className="flex-shrink-0 mt-1">
                        {message.is_read ? (
                          <MailOpen className="h-4 w-4 text-muted-foreground" />
                        ) : (
                          <Mail className="h-4 w-4 text-primary" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <span className={cn(
                            'text-sm truncate',
                            !message.is_read && 'font-semibold'
                          )}>
                            {message.subject || 'Kein Betreff'}
                          </span>
                          <span className="text-xs text-muted-foreground flex-shrink-0">
                            {format(new Date(message.created_at), 'dd.MM.', { locale: de })}
                          </span>
                        </div>
                        <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                          {message.content}
                        </p>
                        <div className="flex items-center gap-1 mt-2">
                          {message.direction === 'inbound' ? (
                            <Building className="h-3 w-3 text-muted-foreground" />
                          ) : (
                            <User className="h-3 w-3 text-muted-foreground" />
                          )}
                          <span className="text-xs text-muted-foreground">
                            {message.direction === 'inbound' ? 'Firma' : 'Sie'}
                          </span>
                        </div>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="p-8 text-center text-muted-foreground">
                <MessageSquare className="mx-auto h-12 w-12 opacity-50 mb-3" />
                <p>Keine Nachrichten vorhanden.</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Message Detail */}
        <Card className="lg:col-span-2">
          <CardContent className="pt-6">
            {selectedMessage ? (
              <div className="space-y-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h2 className="text-xl font-semibold">
                      {selectedMessage.subject || 'Kein Betreff'}
                    </h2>
                    <div className="flex items-center gap-2 mt-2 text-sm text-muted-foreground">
                      {selectedMessage.direction === 'inbound' ? (
                        <>
                          <Building className="h-4 w-4" />
                          <span>Von: Firma</span>
                        </>
                      ) : (
                        <>
                          <User className="h-4 w-4" />
                          <span>Von: Ihnen</span>
                        </>
                      )}
                      <span>•</span>
                      <span>
                        {format(new Date(selectedMessage.created_at), 'dd.MM.yyyy HH:mm', {
                          locale: de,
                        })}
                      </span>
                    </div>
                  </div>
                </div>
                <div className="border-t pt-4">
                  <p className="whitespace-pre-wrap">{selectedMessage.content}</p>
                </div>
                {selectedMessage.direction === 'inbound' && (
                  <div className="border-t pt-4">
                    <Button onClick={() => setDialogOpen(true)}>
                      <Send className="mr-2 h-4 w-4" />
                      Antworten
                    </Button>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex items-center justify-center h-64 text-muted-foreground">
                <div className="text-center">
                  <MessageSquare className="mx-auto h-12 w-12 opacity-50 mb-3" />
                  <p>Wählen Sie eine Nachricht aus</p>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
