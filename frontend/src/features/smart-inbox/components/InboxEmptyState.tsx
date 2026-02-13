import { Inbox } from 'lucide-react';

export function InboxEmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4">
      <Inbox className="h-24 w-24 text-muted-foreground/30 mb-4" />
      <h3 className="text-lg font-semibold mb-2">Keine Einträge</h3>
      <p className="text-sm text-muted-foreground text-center max-w-md">
        Ihr Posteingang ist leer. Neue Dokumente erscheinen hier automatisch
        nach der nächsten Aggregation.
      </p>
    </div>
  );
}
