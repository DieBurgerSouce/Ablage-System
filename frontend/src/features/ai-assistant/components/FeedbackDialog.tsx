/**
 * Feedback Dialog Component
 *
 * Vision 2.0 - Phase 1 (Januar 2026)
 *
 * Allows users to provide feedback on AI assistant responses:
 * - Helpful/Not helpful ratings
 * - Star ratings (1-5)
 * - Free-text comments
 * - Corrections for incorrect responses
 */

import { useState } from 'react';
import {
  ThumbsUp,
  ThumbsDown,
  Star,
  MessageSquare,
  AlertCircle,
  HelpCircle,
  Loader2,
  Check,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { useMessageFeedback, FeedbackType } from '../hooks/use-finance-assistant';

// ===== Types =====

interface FeedbackDialogProps {
  messageId: string;
  messageContent: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
}

interface QuickFeedbackProps {
  messageId: string;
  onDetailedFeedback: () => void;
}

// ===== Quick Feedback Buttons =====

export function QuickFeedback({ messageId, onDetailedFeedback }: QuickFeedbackProps) {
  const { addFeedback, isSubmitting } = useMessageFeedback();
  const [submitted, setSubmitted] = useState<'helpful' | 'not_helpful' | null>(null);

  const handleQuickFeedback = (type: FeedbackType) => {
    addFeedback(
      { messageId, feedbackType: type },
      {
        onSuccess: () => {
          setSubmitted(type as 'helpful' | 'not_helpful');
        },
      }
    );
  };

  if (submitted) {
    return (
      <div className="flex items-center gap-1 text-xs text-muted-foreground">
        <Check className="h-3 w-3 text-green-500" />
        <span>Danke für das Feedback!</span>
      </div>
    );
  }

  return (
    <TooltipProvider>
      <div className="flex items-center gap-1">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={() => handleQuickFeedback('helpful')}
              disabled={isSubmitting}
            >
              <ThumbsUp className="h-3.5 w-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Hilfreich</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={() => handleQuickFeedback('not_helpful')}
              disabled={isSubmitting}
            >
              <ThumbsDown className="h-3.5 w-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Nicht hilfreich</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={onDetailedFeedback}
              disabled={isSubmitting}
            >
              <MessageSquare className="h-3.5 w-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Detailliertes Feedback</TooltipContent>
        </Tooltip>
      </div>
    </TooltipProvider>
  );
}

// ===== Star Rating Component =====

interface StarRatingProps {
  value: number;
  onChange: (value: number) => void;
  disabled?: boolean;
}

function StarRating({ value, onChange, disabled }: StarRatingProps) {
  const [hover, setHover] = useState(0);

  return (
    <div className="flex gap-1">
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          disabled={disabled}
          onMouseEnter={() => setHover(star)}
          onMouseLeave={() => setHover(0)}
          onClick={() => onChange(star)}
          className={cn(
            'p-0.5 transition-colors',
            disabled && 'cursor-not-allowed opacity-50'
          )}
        >
          <Star
            className={cn(
              'h-5 w-5 transition-colors',
              (hover || value) >= star
                ? 'fill-yellow-400 text-yellow-400'
                : 'text-muted-foreground/30'
            )}
          />
        </button>
      ))}
    </div>
  );
}

// ===== Main Dialog Component =====

export function FeedbackDialog({
  messageId,
  messageContent,
  open,
  onOpenChange,
  onSuccess,
}: FeedbackDialogProps) {
  const { addFeedbackAsync, isSubmitting, error } = useMessageFeedback();

  const [feedbackType, setFeedbackType] = useState<FeedbackType>('helpful');
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState('');
  const [correction, setCorrection] = useState('');
  const [expectedIntent, setExpectedIntent] = useState('');

  const feedbackOptions: { value: FeedbackType; label: string; icon: React.ElementType }[] = [
    { value: 'helpful', label: 'Hilfreich', icon: ThumbsUp },
    { value: 'not_helpful', label: 'Nicht hilfreich', icon: ThumbsDown },
    { value: 'incorrect', label: 'Falsch', icon: AlertCircle },
    { value: 'confusing', label: 'Verwirrend', icon: HelpCircle },
  ];

  const handleSubmit = async () => {
    await addFeedbackAsync({
      messageId,
      feedbackType,
      rating: rating > 0 ? rating : undefined,
      comment: comment.trim() || undefined,
      correction: correction.trim() || undefined,
      expectedIntent: expectedIntent.trim() || undefined,
    });

    // Reset form
    setFeedbackType('helpful');
    setRating(0);
    setComment('');
    setCorrection('');
    setExpectedIntent('');

    onOpenChange(false);
    onSuccess?.();
  };

  const showCorrectionField = feedbackType === 'incorrect' || feedbackType === 'not_helpful';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Feedback zur Antwort</DialogTitle>
          <DialogDescription>
            Ihr Feedback hilft uns, den Assistenten zu verbessern.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Original Message Preview */}
          <div className="p-3 bg-muted rounded-lg">
            <p className="text-sm text-muted-foreground line-clamp-3">{messageContent}</p>
          </div>

          {/* Feedback Type */}
          <div className="space-y-2">
            <Label>Wie war die Antwort?</Label>
            <RadioGroup
              value={feedbackType}
              onValueChange={(v) => setFeedbackType(v as FeedbackType)}
              className="grid grid-cols-2 gap-2"
            >
              {feedbackOptions.map((option) => {
                const Icon = option.icon;
                return (
                  <Label
                    key={option.value}
                    htmlFor={option.value}
                    className={cn(
                      'flex items-center gap-2 p-3 rounded-lg border cursor-pointer transition-colors',
                      feedbackType === option.value
                        ? 'border-primary bg-primary/5'
                        : 'hover:bg-muted/50'
                    )}
                  >
                    <RadioGroupItem value={option.value} id={option.value} className="sr-only" />
                    <Icon className="h-4 w-4" />
                    <span className="text-sm">{option.label}</span>
                  </Label>
                );
              })}
            </RadioGroup>
          </div>

          {/* Star Rating */}
          <div className="space-y-2">
            <Label>Bewertung (optional)</Label>
            <StarRating value={rating} onChange={setRating} disabled={isSubmitting} />
          </div>

          {/* Comment */}
          <div className="space-y-2">
            <Label htmlFor="comment">Kommentar (optional)</Label>
            <Textarea
              id="comment"
              placeholder="Was könnten wir besser machen?"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              disabled={isSubmitting}
              rows={3}
            />
          </div>

          {/* Correction Field (for incorrect/not_helpful) */}
          {showCorrectionField && (
            <div className="space-y-2">
              <Label htmlFor="correction">Korrektur (optional)</Label>
              <Textarea
                id="correction"
                placeholder="Was waere die richtige Antwort gewesen?"
                value={correction}
                onChange={(e) => setCorrection(e.target.value)}
                disabled={isSubmitting}
                rows={3}
              />
            </div>
          )}

          {/* Error Display */}
          {error && (
            <div className="p-3 bg-destructive/10 text-destructive rounded-lg text-sm">
              {error.message}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isSubmitting}>
            Abbrechen
          </Button>
          <Button onClick={handleSubmit} disabled={isSubmitting}>
            {isSubmitting ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Wird gesendet...
              </>
            ) : (
              'Feedback senden'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default FeedbackDialog;
