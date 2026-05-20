import { useState, useEffect, useMemo } from 'react';

type ThinkingPhase = 'initial' | 'searching' | 'analyzing' | 'generating';

interface ThinkingMessagesConfig {
    /** Ob ein Dokument angehängt wurde */
    hasAttachment: boolean;
    /** Ob bereits Content gestreamt wird */
    hasContent: boolean;
    /** Ob aktiv gestreamt wird */
    isStreaming: boolean;
    /** Ob im Thinking-Modus (vor Streaming) */
    isThinking: boolean;
}

// Nachrichten-Sets für verschiedene Phasen
const MESSAGES: Record<ThinkingPhase, string[]> = {
    // Initiale Phase - Anfrage wird verarbeitet
    initial: [
        'Verarbeite Anfrage...',
        'Bereite Antwort vor...',
        'Initialisiere...',
    ],
    // RAG-Suche in Dokumenten (ohne Attachment)
    searching: [
        'Suche in Dokumenten...',
        'Durchsuche Archiv...',
        'Finde relevante Quellen...',
        'Analysiere Dokumente...',
    ],
    // Dokument-Analyse (mit Attachment)
    analyzing: [
        'Analysiere Dokument...',
        'Lese Dokumentinhalt...',
        'Extrahiere Informationen...',
        'Verarbeite Anhang...',
    ],
    // Antwort wird generiert (hat bereits etwas Content)
    generating: [
        'Generiere Antwort...',
        'Formuliere Text...',
        'Schreibe Antwort...',
    ],
};

// Intervall für Nachrichtenwechsel (in ms)
const ROTATION_INTERVAL = 2500;

/**
 * Hook für rotierende, kontextabhängige Thinking-Nachrichten.
 *
 * Passt die Nachrichten an den aktuellen Zustand an:
 * - Mit Dokument-Anhang: "Analysiere Dokument..."
 * - Ohne Anhang: "Suche in Dokumenten..."
 * - Mit bereits generiertem Content: "Generiere Antwort..."
 *
 * @example
 * const message = useThinkingMessage({
 *     hasAttachment: !!attachedDocument,
 *     hasContent: streamingContent.length > 0,
 *     isStreaming,
 *     isThinking
 * });
 */
export function useThinkingMessage(config: ThinkingMessagesConfig): string {
    const { hasAttachment, hasContent, isStreaming, isThinking } = config;
    const [messageIndex, setMessageIndex] = useState(0);

    // Bestimme die aktuelle Phase basierend auf dem Kontext
    const phase = useMemo((): ThinkingPhase => {
        // Wenn bereits Content generiert wird
        if (hasContent && isStreaming) {
            return 'generating';
        }
        // Wenn ein Dokument angehängt ist
        if (hasAttachment) {
            return 'analyzing';
        }
        // Wenn noch am Anfang (isThinking aber noch kein Streaming)
        if (isThinking && !isStreaming) {
            return 'initial';
        }
        // Standard: Suche in Dokumenten
        return 'searching';
    }, [hasAttachment, hasContent, isStreaming, isThinking]);

    const messages = MESSAGES[phase];

    // Rotiere durch die Nachrichten
    useEffect(() => {
        // Nur rotieren wenn aktiv (thinking oder streaming ohne content)
        const isActive = isThinking || (isStreaming && !hasContent);
        if (!isActive) {
            // eslint-disable-next-line react-hooks/set-state-in-effect -- Intentional reset when becoming inactive
            setMessageIndex(0);
            return;
        }

        const interval = setInterval(() => {
            setMessageIndex((prev) => (prev + 1) % messages.length);
        }, ROTATION_INTERVAL);

        return () => clearInterval(interval);
    }, [isThinking, isStreaming, hasContent, messages.length]);

    // Reset index wenn sich die Phase ändert
    useEffect(() => {
        // eslint-disable-next-line react-hooks/set-state-in-effect -- Intentional reset on phase change
        setMessageIndex(0);
    }, [phase]);

    return messages[messageIndex];
}

export default useThinkingMessage;
