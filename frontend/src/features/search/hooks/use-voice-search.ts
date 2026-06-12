import { useState, useCallback, useRef, useEffect } from 'react';

// ============================================================================
// Web-Speech-API-Typen (nicht Teil von lib.dom; minimale Deklarationen)
// ============================================================================

interface SpeechRecognitionAlternative {
  transcript: string;
  confidence: number;
}

interface SpeechRecognitionResult {
  isFinal: boolean;
  readonly length: number;
  [index: number]: SpeechRecognitionAlternative;
}

interface SpeechRecognitionResultList {
  readonly length: number;
  [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionEvent extends Event {
  resultIndex: number;
  results: SpeechRecognitionResultList;
}

interface SpeechRecognitionErrorEvent extends Event {
  error: string;
  message: string;
}

interface SpeechRecognition extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

declare const SpeechRecognition: {
  prototype: SpeechRecognition;
  new (): SpeechRecognition;
};


/**
 * Options for the useVoiceSearch hook
 */
export interface UseVoiceSearchOptions {
  /** Language for speech recognition (default: 'de-DE') */
  language?: string;
  /** Whether to continue listening after a result (default: false) */
  continuous?: boolean;
  /** Callback when a transcript is finalized */
  onTranscript?: (text: string) => void;
  /** Callback when an error occurs */
  onError?: (error: string) => void;
}

/**
 * Return type for the useVoiceSearch hook
 */
export interface UseVoiceSearchReturn {
  /** Whether the speech recognition is currently listening */
  isListening: boolean;
  /** Whether speech recognition is supported in this browser */
  isSupported: boolean;
  /** The current transcript text */
  transcript: string;
  /** Error message if recognition failed */
  error: string | null;
  /** Start listening for speech */
  startListening: () => void;
  /** Stop listening for speech */
  stopListening: () => void;
  /** Clear the current transcript */
  resetTranscript: () => void;
}

/**
 * Error messages in German for speech recognition errors
 */
const ERROR_MESSAGES: Record<string, string> = {
  'not-allowed': 'Mikrofon-Zugriff verweigert',
  'no-speech': 'Keine Sprache erkannt',
  'network': 'Netzwerkfehler bei Spracherkennung',
  'audio-capture': 'Mikrofon nicht verfuegbar',
  'not-supported': 'Spracherkennung wird nicht unterstuetzt',
};

/**
 * Custom React hook for Web Speech API voice recognition
 *
 * @param options - Configuration options
 * @returns Voice search state and control functions
 *
 * @example
 * ```tsx
 * const { isListening, transcript, startListening, stopListening } = useVoiceSearch({
 *   language: 'de-DE',
 *   onTranscript: (text) => console.log('Final:', text),
 * });
 * ```
 */
export function useVoiceSearch(options: UseVoiceSearchOptions = {}): UseVoiceSearchReturn {
  const {
    language = 'de-DE',
    continuous = false,
    onTranscript,
    onError,
  } = options;

  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [error, setError] = useState<string | null>(null);

  const recognitionRef = useRef<SpeechRecognition | null>(null);

  // Check if speech recognition is supported
  const isSupported = typeof window !== 'undefined' &&
    ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window);

  /**
   * Initialize the speech recognition instance
   */
  const initializeRecognition = useCallback(() => {
    if (!isSupported) {
      return null;
    }

    // Use the prefixed version if needed
    const SpeechRecognitionAPI =
      (window as typeof window & { SpeechRecognition?: typeof SpeechRecognition }).SpeechRecognition ||
      (window as typeof window & { webkitSpeechRecognition?: typeof SpeechRecognition }).webkitSpeechRecognition;

    if (!SpeechRecognitionAPI) {
      return null;
    }

    const recognition = new SpeechRecognitionAPI();
    recognition.lang = language;
    recognition.continuous = continuous;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    // Handle interim and final results
    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let interimTranscript = '';
      let finalTranscript = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          finalTranscript += result[0].transcript;
        } else {
          interimTranscript += result[0].transcript;
        }
      }

      // Update transcript with interim or final result
      const currentTranscript = finalTranscript || interimTranscript;
      setTranscript(currentTranscript);

      // If we have a final result, call the callback
      if (finalTranscript && onTranscript) {
        onTranscript(finalTranscript.trim());
      }
    };

    // Handle errors
    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      const errorMessage = ERROR_MESSAGES[event.error] || ERROR_MESSAGES['not-supported'];
      setError(errorMessage);
      setIsListening(false);

      if (onError) {
        onError(errorMessage);
      }
    };

    // Handle end of recognition
    recognition.onend = () => {
      setIsListening(false);
    };

    return recognition;
  }, [isSupported, language, continuous, onTranscript, onError]);

  /**
   * Start listening for speech
   */
  const startListening = useCallback(() => {
    if (!isSupported) {
      const errorMessage = ERROR_MESSAGES['not-supported'];
      setError(errorMessage);
      if (onError) {
        onError(errorMessage);
      }
      return;
    }

    // Clear previous errors
    setError(null);
    setTranscript('');

    // Initialize or reuse recognition
    if (!recognitionRef.current) {
      recognitionRef.current = initializeRecognition();
    }

    if (recognitionRef.current) {
      try {
        recognitionRef.current.start();
        setIsListening(true);
      } catch (err) {
        // If already started, this will throw an error - ignore it
        if (err instanceof Error && !err.message.includes('already started')) {
          const errorMessage = ERROR_MESSAGES['not-supported'];
          setError(errorMessage);
          if (onError) {
            onError(errorMessage);
          }
        }
      }
    }
  }, [isSupported, initializeRecognition, onError]);

  /**
   * Stop listening for speech
   */
  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      setIsListening(false);
    }
  }, []);

  /**
   * Clear the current transcript
   */
  const resetTranscript = useCallback(() => {
    setTranscript('');
    setError(null);
  }, []);

  /**
   * Cleanup on unmount
   */
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
        recognitionRef.current = null;
      }
    };
  }, []);

  return {
    isListening,
    isSupported,
    transcript,
    error,
    startListening,
    stopListening,
    resetTranscript,
  };
}
