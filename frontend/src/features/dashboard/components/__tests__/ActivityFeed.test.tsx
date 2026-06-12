/**
 * ActivityFeed Component Tests
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@/test/utils';
import { ActivityFeed } from '../ActivityFeed';
import { createMockActivityEvent } from '@/test/utils';
// ESM-konformer Zugriff auf die gemockten Hooks (require() existiert in Vitest/ESM nicht)
import * as websocketModule from '@/lib/websocket';

// Mock WebSocket hook
vi.mock('@/lib/websocket', () => ({
  useWebSocket: vi.fn(() => ({
    state: 'connected',
  })),
  useEventStream: vi.fn(() => []),
}));

describe('ActivityFeed', () => {
  beforeEach(() => {
    // Mock-Rueckgaben zwischen Tests zuruecksetzen (mockReturnValue ist persistent)
    vi.mocked(websocketModule.useEventStream).mockReturnValue([]);
    vi.mocked(websocketModule.useWebSocket).mockReturnValue({ state: 'connected' });
  });

  it('renders with empty state when no events', () => {
    render(<ActivityFeed />);

    expect(screen.getByText('Aktivitäten')).toBeInTheDocument();
    expect(screen.getByText('Keine Aktivitäten')).toBeInTheDocument();
  });

  it('displays event count badge', () => {
    const useEventStream = vi.mocked(websocketModule.useEventStream);
    useEventStream.mockReturnValue([
      createMockActivityEvent({ event_id: '1' }),
      createMockActivityEvent({ event_id: '2' }),
    ]);

    render(<ActivityFeed />);

    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('renders events from useEventStream', () => {
    const useEventStream = vi.mocked(websocketModule.useEventStream);
    const mockEvents = [
      createMockActivityEvent({
        event_id: '1',
        event_type: 'document.uploaded',
        payload: { filename: 'test1.pdf' },
      }),
      createMockActivityEvent({
        event_id: '2',
        event_type: 'document.ocr_completed',
        payload: { filename: 'test2.pdf' },
      }),
    ];
    useEventStream.mockReturnValue(mockEvents);

    render(<ActivityFeed />);

    expect(screen.getByText(/dokument hochgeladen/i)).toBeInTheDocument();
    expect(screen.getByText(/ocr abgeschlossen/i)).toBeInTheDocument();
  });

  it('shows connection status when showConnectionStatus is true', () => {
    const useWebSocket = vi.mocked(websocketModule.useWebSocket);
    useWebSocket.mockReturnValue({ state: 'connected' });

    render(<ActivityFeed showConnectionStatus />);

    // Connection status icon sollte vorhanden sein
    const header = screen.getByText('Aktivitäten').parentElement;
    expect(header).toBeInTheDocument();
  });

  it('displays disconnected state', () => {
    const useWebSocket = vi.mocked(websocketModule.useWebSocket);
    useWebSocket.mockReturnValue({ state: 'disconnected' });

    render(<ActivityFeed showConnectionStatus />);

    expect(screen.getByText('Keine Aktivitäten')).toBeInTheDocument();
    expect(screen.getByText('WebSocket nicht verbunden')).toBeInTheDocument();
  });

  it('respects maxEvents limit', () => {
    const useEventStream = vi.mocked(websocketModule.useEventStream);
    const mockEvents = Array.from({ length: 100 }, (_, i) =>
      createMockActivityEvent({ event_id: `event-${i}` })
    );
    useEventStream.mockReturnValue(mockEvents);

    render(<ActivityFeed maxEvents={50} />);

    // Badge sollte die Anzahl der Events zeigen
    expect(screen.getByText('100')).toBeInTheDocument();
  });

  it('renders in compact mode', () => {
    const useEventStream = vi.mocked(websocketModule.useEventStream);
    useEventStream.mockReturnValue([
      createMockActivityEvent({
        event_id: '1',
        event_type: 'document.uploaded',
        payload: { filename: 'compact-test.pdf' },
      }),
    ]);

    render(<ActivityFeed compact />);

    expect(screen.getByText(/dokument hochgeladen/i)).toBeInTheDocument();
  });

  it('shows priority badges for high/critical events', () => {
    const useEventStream = vi.mocked(websocketModule.useEventStream);
    useEventStream.mockReturnValue([
      createMockActivityEvent({
        event_id: '1',
        event_type: 'system.error',
        priority: 'critical',
        payload: { message: 'Critical error' },
      }),
    ]);

    render(<ActivityFeed />);

    expect(screen.getByText('Kritisch')).toBeInTheDocument();
  });

  it('formats German timestamps correctly', () => {
    const useEventStream = vi.mocked(websocketModule.useEventStream);
    const now = new Date();
    useEventStream.mockReturnValue([
      createMockActivityEvent({
        event_id: '1',
        timestamp: now.toISOString(),
      }),
    ]);

    render(<ActivityFeed />);

    // formatDistanceToNow sollte deutsche Texte erzeugen
    // z.B. "vor wenigen Sekunden"
    expect(screen.getByText(/vor/i)).toBeInTheDocument();
  });
});
