/**
 * Checklist Event Bus
 *
 * Ermoeglicht event-driven Completion von Checklist-Items.
 * Wenn der User z.B. einen Workflow speichert, wird automatisch
 * das Checklist-Item 'create_workflow' als erledigt markiert.
 */

import { useEffect } from 'react';

const CHECKLIST_EVENT_NAME = 'ablage:checklist-complete';

/**
 * Emit: markiert ein Checklist-Item als erledigt.
 * Kann von jeder Komponente aufgerufen werden.
 */
export function emitChecklistComplete(itemId: string): void {
  window.dispatchEvent(
    new CustomEvent(CHECKLIST_EVENT_NAME, { detail: { itemId } }),
  );
}

/**
 * Listener-Hook: ruft onComplete auf, wenn ein Checklist-Item
 * per Event als erledigt gemeldet wird.
 */
export function useChecklistListener(
  onComplete: (itemId: string) => void,
): void {
  useEffect(() => {
    function handler(event: Event) {
      const customEvent = event as CustomEvent<{ itemId: string }>;
      if (customEvent.detail?.itemId) {
        onComplete(customEvent.detail.itemId);
      }
    }

    window.addEventListener(CHECKLIST_EVENT_NAME, handler);
    return () => {
      window.removeEventListener(CHECKLIST_EVENT_NAME, handler);
    };
  }, [onComplete]);
}
