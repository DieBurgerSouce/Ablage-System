import { useState } from "react";
import { MessageSquare, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { CommentReply } from "../types/annotations-extended-types";
import { MentionInput } from "./MentionInput";

interface CommentReplyThreadProps {
  commentId: number;
  originalComment: {
    author: string;
    content: string;
    createdAt: Date;
  };
  replies: CommentReply[];
  onReply: (content: string, mentions: string[]) => void;
  userSuggestions?: string[];
}

export function CommentReplyThread({
  commentId,
  originalComment,
  replies,
  onReply,
  userSuggestions = [],
}: CommentReplyThreadProps) {
  const [replyContent, setReplyContent] = useState("");
  const [mentions, setMentions] = useState<string[]>([]);

  const handleSubmitReply = () => {
    if (!replyContent.trim()) return;

    onReply(replyContent, mentions);
    setReplyContent("");
    setMentions([]);
  };

  const formatDate = (date: Date) => {
    return new Intl.DateTimeFormat("de-DE", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  };

  const getInitials = (name: string) => {
    return name
      .split(" ")
      .map((n) => n[0])
      .join("")
      .toUpperCase()
      .slice(0, 2);
  };

  const highlightMentions = (text: string, mentionsList: string[]) => {
    if (!mentionsList.length) return text;

    const parts: React.ReactNode[] = [];
    let lastIndex = 0;

    mentionsList.forEach((mention) => {
      const mentionText = `@${mention}`;
      const index = text.indexOf(mentionText, lastIndex);

      if (index !== -1) {
        // Add text before mention
        if (index > lastIndex) {
          parts.push(text.substring(lastIndex, index));
        }

        // Add highlighted mention
        parts.push(
          <span
            key={`mention-${index}`}
            className="text-blue-600 font-medium bg-blue-50 px-1 rounded"
          >
            {mentionText}
          </span>
        );

        lastIndex = index + mentionText.length;
      }
    });

    // Add remaining text
    if (lastIndex < text.length) {
      parts.push(text.substring(lastIndex));
    }

    return parts.length > 0 ? parts : text;
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MessageSquare className="w-5 h-5" />
          Diskussion
        </CardTitle>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Original Comment */}
        <div className="flex gap-3">
          <Avatar className="w-8 h-8">
            <AvatarFallback className="bg-blue-500 text-white text-xs">
              {getInitials(originalComment.author)}
            </AvatarFallback>
          </Avatar>

          <div className="flex-1 space-y-1">
            <div className="flex items-baseline gap-2">
              <span className="font-medium text-sm">
                {originalComment.author}
              </span>
              <span className="text-xs text-muted-foreground">
                {formatDate(originalComment.createdAt)}
              </span>
            </div>
            <p className="text-sm text-gray-700 dark:text-gray-300">
              {originalComment.content}
            </p>
          </div>
        </div>

        <Separator />

        {/* Replies */}
        {replies.length > 0 && (
          <ScrollArea className="max-h-96">
            <div className="space-y-4">
              {replies.map((reply) => (
                <div key={reply.id} className="flex gap-3 ml-6">
                  <Avatar className="w-7 h-7">
                    <AvatarFallback className="bg-gray-500 text-white text-xs">
                      {getInitials(reply.author)}
                    </AvatarFallback>
                  </Avatar>

                  <div className="flex-1 space-y-1">
                    <div className="flex items-baseline gap-2">
                      <span className="font-medium text-sm">{reply.author}</span>
                      <span className="text-xs text-muted-foreground">
                        {formatDate(reply.createdAt)}
                      </span>
                    </div>
                    <p className="text-sm text-gray-700 dark:text-gray-300">
                      {highlightMentions(reply.content, reply.mentions)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        )}

        <Separator />

        {/* Reply Input */}
        <div className="space-y-2">
          <label className="text-sm font-medium">Antworten</label>
          <MentionInput
            value={replyContent}
            onChange={setReplyContent}
            onMention={(mention) => setMentions([...mentions, mention])}
            userSuggestions={userSuggestions}
            placeholder="Ihre Antwort... (@ für Erwähnungen)"
            rows={3}
          />

          <div className="flex justify-end">
            <Button
              onClick={handleSubmitReply}
              disabled={!replyContent.trim()}
              size="sm"
            >
              <Send className="w-4 h-4 mr-2" />
              Antworten
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
