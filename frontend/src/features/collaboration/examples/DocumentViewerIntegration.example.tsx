/**
 * EXAMPLE: Document Viewer mit Collaboration Features
 *
 * Dieser Beispiel zeigt die Integration aller Collaboration-Features
 * in einem Dokument-Viewer.
 *
 * NICHT IN PRODUCTION VERWENDEN - NUR ALS REFERENZ!
 */

import { useState } from 'react';
import { useParams } from '@tanstack/react-router';
import { Button } from '@/components/ui/button';
import { Lock, Unlock } from 'lucide-react';
import {
  // Hooks
  useDocumentLock,
  usePresence,
  useDocumentActivityRealtime,
  // Components
  PresenceIndicator,
  DocumentLockBanner,
  ActivityTimeline,
  MentionsBadge,
  // Existing
  CommentsPanel,
} from '@/features/collaboration';

// ==================== Example Document Viewer ====================

export function DocumentViewerWithCollaboration() {
  const { documentId } = useParams({ from: '/documents/$documentId' });
  const currentUserId = 'user-123'; // TODO: Get from auth context

  // Document Lock
  const {
    isLocked,
    lock,
    isLockedByMe,
    canEdit,
    toggleLock,
    isToggling,
  } = useDocumentLock(documentId, currentUserId);

  // Presence (wer schaut gerade)
  const { viewers } = usePresence(documentId);

  // Activity Feed
  const { activities } = useDocumentActivityRealtime(documentId);

  // UI State
  const [showActivityTimeline, setShowActivityTimeline] = useState(false);

  const handleForceLock = async () => {
    // Force lock übernimmt die Sperre von anderem Benutzer
    await toggleLock();
  };

  return (
    <div className="flex flex-col h-screen">
      {/* Header mit Presence + Lock */}
      <div className="border-b px-6 py-3 flex items-center justify-between bg-background">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-semibold">Dokument Viewer</h1>

          {/* Presence Indicator */}
          <PresenceIndicator viewers={viewers} currentUserId={currentUserId} />
        </div>

        <div className="flex items-center gap-2">
          {/* Mentions Badge */}
          <MentionsBadge showPreview />

          {/* Lock/Unlock Toggle */}
          <Button
            variant={isLockedByMe ? 'default' : 'outline'}
            size="sm"
            onClick={toggleLock}
            disabled={isToggling || (isLocked && !isLockedByMe)}
          >
            {isLockedByMe ? (
              <>
                <Unlock className="h-4 w-4 mr-2" />
                Sperre aufheben
              </>
            ) : (
              <>
                <Lock className="h-4 w-4 mr-2" />
                Dokument sperren
              </>
            )}
          </Button>

          {/* Activity Timeline Toggle */}
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowActivityTimeline(!showActivityTimeline)}
          >
            {showActivityTimeline ? 'Timeline ausblenden' : 'Timeline anzeigen'}
          </Button>
        </div>
      </div>

      {/* Lock Banner */}
      {isLocked && !isLockedByMe && lock && (
        <DocumentLockBanner
          lock={lock}
          currentUserId={currentUserId}
          onForceLock={handleForceLock}
          isForcing={isToggling}
          variant="warning"
          className="m-4"
        />
      )}

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Document Content */}
        <div className="flex-1 overflow-auto p-6">
          <div className="max-w-4xl mx-auto">
            {/* Document Content hier... */}
            <div className="prose prose-sm">
              <h2>Dokument Inhalt</h2>
              <p>Lorem ipsum dolor sit amet...</p>
            </div>

            {/* Comments Section */}
            <div className="mt-8 border-t pt-8">
              <CommentsPanel
                documentId={documentId}
                currentUserId={currentUserId}
                canComment={canEdit}
              />
            </div>
          </div>
        </div>

        {/* Activity Timeline Sidebar */}
        {showActivityTimeline && (
          <div className="w-96 border-l bg-muted/20">
            <ActivityTimeline
              activities={activities}
              height="calc(100vh - 64px)"
              groupByDate
            />
          </div>
        )}
      </div>
    </div>
  );
}

// ==================== Example Toolbar Integration ====================

export function DocumentToolbarWithCollaboration() {
  const { documentId } = useParams({ from: '/documents/$documentId' });
  const currentUserId = 'user-123';

  const { viewers } = usePresence(documentId);
  const { isLockedByMe, toggleLock, isToggling } = useDocumentLock(
    documentId,
    currentUserId
  );

  return (
    <div className="flex items-center gap-3 px-4 py-2 border-b">
      {/* Compact Presence */}
      <PresenceIndicator
        viewers={viewers}
        currentUserId={currentUserId}
        maxVisible={3}
        size="sm"
        showText={false}
      />

      <div className="h-5 w-px bg-border" />

      {/* Lock Toggle */}
      <Button
        variant="ghost"
        size="sm"
        onClick={toggleLock}
        disabled={isToggling}
        className="h-8"
      >
        {isLockedByMe ? <Unlock className="h-3.5 w-3.5" /> : <Lock className="h-3.5 w-3.5" />}
      </Button>

      {/* Mentions Badge */}
      <MentionsBadge showPreview={false} />
    </div>
  );
}

// ==================== Example Dashboard Widget ====================

export function RecentActivityWidget() {
  const { activities } = useUserActivityFeed({ limit: 10 });

  return (
    <ActivityTimeline
      activities={activities}
      height="300px"
      groupByDate={false}
      showAvatars
      emptyMessage="Keine aktuellen Aktivitäten"
    />
  );
}
