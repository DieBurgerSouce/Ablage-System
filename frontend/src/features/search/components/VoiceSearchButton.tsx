import { Mic, MicOff, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { useVoiceSearch } from '../hooks/use-voice-search';

/**
 * Props for the VoiceSearchButton component
 */
export interface VoiceSearchButtonProps {
  /** Callback when a final transcript is received */
  onTranscript: (text: string) => void;
  /** Additional CSS classes */
  className?: string;
  /** Whether the button is disabled */
  disabled?: boolean;
}

/**
 * Voice Search Button Component
 *
 * Provides a microphone button for voice-to-text search using the Web Speech API.
 * Supports German (de-DE) speech recognition with visual feedback.
 *
 * @example
 * ```tsx
 * <VoiceSearchButton
 *   onTranscript={(text) => handleSearch(text)}
 *   disabled={isSearching}
 * />
 * ```
 */
export function VoiceSearchButton({
  onTranscript,
  className,
  disabled = false,
}: VoiceSearchButtonProps) {
  const {
    isListening,
    isSupported,
    transcript,
    startListening,
    stopListening,
  } = useVoiceSearch({
    language: 'de-DE',
    continuous: false,
    onTranscript,
  });

  /**
   * Toggle listening state
   */
  const handleClick = () => {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  };

  /**
   * Get tooltip text based on current state
   */
  const getTooltipText = () => {
    if (!isSupported) {
      return 'Spracherkennung wird in diesem Browser nicht unterstuetzt';
    }
    if (isListening) {
      return 'Sprachsuche beenden';
    }
    return 'Sprachsuche starten (de-DE)';
  };

  /**
   * Get the icon based on current state
   */
  const getIcon = () => {
    if (!isSupported) {
      return <MicOff className="h-4 w-4" />;
    }
    if (isListening && transcript) {
      return <Loader2 className="h-4 w-4 animate-spin" />;
    }
    if (isListening) {
      return <Mic className="h-4 w-4 text-red-500" />;
    }
    return <Mic className="h-4 w-4" />;
  };

  const isDisabled = disabled || !isSupported;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div className="relative">
          {/* Pulse animation ring when listening */}
          {isListening && (
            <span className="absolute inset-0 flex items-center justify-center">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-400 opacity-75" />
            </span>
          )}

          {/* Button */}
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={handleClick}
            disabled={isDisabled}
            className={cn(
              'relative',
              isListening && 'bg-red-50 hover:bg-red-100 dark:bg-red-950 dark:hover:bg-red-900',
              className
            )}
            aria-label={isListening ? 'Sprachsuche beenden' : 'Sprachsuche starten'}
            aria-pressed={isListening}
          >
            {getIcon()}
          </Button>
        </div>
      </TooltipTrigger>
      <TooltipContent>
        <p>{getTooltipText()}</p>
      </TooltipContent>
    </Tooltip>
  );
}
