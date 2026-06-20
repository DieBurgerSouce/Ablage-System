/**
 * B5-Regression: Notifications-Contract
 *
 * ECHTER Backend-Vertrag (app/api/v1/notifications.py +
 * app/db/schemas.py::NotificationsListResponse):
 *
 *   GET /api/v1/notifications/?page=&per_page=
 *   -> { "notifications": [ { id, type, title, message, isRead, createdAt,
 *        actionUrl, ... } ], "unreadCount": n, "total": n }
 *
 * Vorher erwartete das Frontend faelschlich { items: [...] }:
 * data.pages.flatMap((page) => page.items) lieferte [undefined]
 * -> TypeError in .filter(n => n.snoozed_until)
 * -> Root-ErrorBoundary ersetzte die GESAMTE App auf JEDER Route
 *    (1-3s nach Mount, sobald die Query resolved).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import { createTestQueryClient } from '@/test/utils';
import { apiClient } from '@/lib/api';
import { NotificationCenter } from '../components/NotificationCenter';
import { getNotifications, getUnreadCount, normalizeNotification } from '../api';
import { notificationKeys } from '../hooks/useNotifications';

vi.mock('@/lib/api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn()
  }
}));

// NotificationItem nutzt useNavigate - ohne echten Router-Kontext mocken
vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@tanstack/react-router')>();
  return { ...actual, useNavigate: () => vi.fn() };
});

const mockedGet = apiClient.get as unknown as ReturnType<typeof vi.fn>;

/** Antwort EXAKT im echten Backend-Shape (Legacy camelCase-Felder). */
const realBackendResponse = {
  notifications: [
    {
      id: 'b5-n1',
      type: 'document_shared',
      title: 'Dokument geteilt',
      message: 'Max Mustermann hat ein Dokument mit Ihnen geteilt',
      documentId: 'doc-1',
      documentName: 'rechnung.pdf',
      fromUserId: 'user-1',
      fromUserName: 'Max Mustermann',
      fromUserAvatar: null,
      isRead: false,
      createdAt: new Date().toISOString(),
      actionUrl: '/documents/doc-1'
    },
    {
      id: 'b5-n2',
      type: 'comment',
      title: 'Neuer Kommentar',
      message: 'Erika Musterfrau hat einen Kommentar hinterlassen',
      documentId: null,
      documentName: null,
      fromUserId: 'user-2',
      fromUserName: 'Erika Musterfrau',
      fromUserAvatar: null,
      isRead: true,
      createdAt: new Date().toISOString(),
      actionUrl: null
    }
  ],
  unreadCount: 1,
  total: 2
};

function renderCenter(queryClient = createTestQueryClient()) {
  return render(
    <QueryClientProvider client={queryClient}>
      <div>App lebt</div>
      <NotificationCenter open onOpenChange={() => {}} />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('Notifications-API normalisiert den echten Backend-Vertrag (B5)', () => {
  it('mappt {notifications, unreadCount, total} auf das Frontend-Schema', async () => {
    mockedGet.mockResolvedValueOnce({ data: realBackendResponse });

    const result = await getNotifications({ page: 1, page_size: 20 });

    expect(result.items).toHaveLength(2);
    expect(result.items[0]).toMatchObject({
      id: 'b5-n1',
      title: 'Dokument geteilt',
      read: false,
      link: '/documents/doc-1',
      priority: 'info'
    });
    expect(result.items[0].created_at).toBe(
      realBackendResponse.notifications[0].createdAt
    );
    expect(result.items[1].read).toBe(true);
    expect(result.total).toBe(2);
    expect(result.has_more).toBe(false);

    // Pagination muss als per_page (echter Vertrag) rausgehen
    const requestedUrl = mockedGet.mock.calls[0][0] as string;
    expect(requestedUrl).toContain('per_page=20');
    expect(requestedUrl).not.toContain('page_size');
  });

  it('liest unreadCount aus dem echten unread-count-Vertrag', async () => {
    mockedGet.mockResolvedValueOnce({
      data: { unreadCount: 7, systemCount: 4, userCount: 3 }
    });

    await expect(getUnreadCount()).resolves.toBe(7);
  });

  it('verwirft unbrauchbare Roh-Eintraege statt zu crashen', () => {
    expect(normalizeNotification(null)).toBeNull();
    expect(normalizeNotification(42)).toBeNull();
    expect(normalizeNotification({})).toBeNull();
    expect(normalizeNotification({ id: '' })).toBeNull();
    expect(normalizeNotification({ id: 'ok' })).toMatchObject({
      id: 'ok',
      read: false,
      priority: 'info'
    });
  });
});

describe('NotificationCenter mit echtem Response-Shape (B5)', () => {
  it('rendert Benachrichtigungen ohne Absturz', async () => {
    mockedGet.mockResolvedValue({ data: realBackendResponse });

    renderCenter();

    expect(await screen.findByText('Dokument geteilt')).toBeInTheDocument();
    expect(screen.getByText('Neuer Kommentar')).toBeInTheDocument();
    // Der umgebende Baum lebt
    expect(screen.getByText('App lebt')).toBeInTheDocument();
  });

  it('zeigt bei lauter kaputten Eintraegen den leeren Zustand (kein Crash)', async () => {
    mockedGet.mockResolvedValue({
      data: {
        notifications: [null, 42, {}, { id: '' }],
        unreadCount: 0,
        total: 4
      }
    });

    renderCenter();

    expect(
      await screen.findByText('Keine Benachrichtigungen')
    ).toBeInTheDocument();
    expect(screen.getByText('App lebt')).toBeInTheDocument();
  });

  it('lokale ErrorBoundary: Crash im Widget toetet nicht den umgebenden Baum', async () => {
    const queryClient = createTestQueryClient();
    // Vergifteter Query-Cache simuliert einen unerwarteten Renderfehler
    // im Inneren des Widgets (pages ist kein Array -> flatMap wirft).
    queryClient.setQueryData(notificationKeys.list(undefined), {
      pages: 'kaputt',
      pageParams: [1]
    });
    // React loggt gefangene Fehler auf console.error - still halten
    const consoleError = vi
      .spyOn(console, 'error')
      .mockImplementation(() => {});

    try {
      renderCenter(queryClient);

      expect(
        await screen.findByText('Benachrichtigungen nicht verfügbar')
      ).toBeInTheDocument();
      // Die App drumherum lebt weiter
      expect(screen.getByText('App lebt')).toBeInTheDocument();
    } finally {
      consoleError.mockRestore();
    }
  });
});
