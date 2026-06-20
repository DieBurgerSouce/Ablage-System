/**
 * OfflineDocumentList Component
 *
 * Displays cached documents available for offline viewing.
 * Features:
 * - List of cached documents
 * - Cache management (clear, refresh)
 * - Storage usage display
 */

import * as React from 'react';
import {
  FileText,
  Trash2,
  RefreshCw,
  HardDrive,
  Calendar,
  Clock,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { cn } from '@/lib/utils';
import {
  getAllCachedDocuments,
  clearExpiredDocuments,
  getStorageEstimate,
  type CachedDocument,
} from '@/lib/storage/indexed-db';
import { logger } from '@/lib/logger';

// ============================================
// Types
// ============================================

export interface OfflineDocumentListProps {
  /** Called when a document is selected */
  onSelectDocument?: (doc: CachedDocument) => void;
  /** Custom className */
  className?: string;
  /** Maximum height (default: 400px) */
  maxHeight?: string;
}

interface StorageInfo {
  usage: number;
  quota: number;
  percentUsed: number;
}

// ============================================
// Utility Functions
// ============================================

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

function formatDate(timestamp: number): string {
  return new Date(timestamp).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}


function getTimeUntilExpiry(expiresAt: number): string {
  const now = Date.now();
  const diff = expiresAt - now;

  if (diff <= 0) return 'Abgelaufen';

  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));

  if (days > 0) return `${days} Tage`;
  if (hours > 0) return `${hours} Stunden`;
  return 'Weniger als 1 Stunde';
}

// ============================================
// Component
// ============================================

export function OfflineDocumentList({
  onSelectDocument,
  className,
  maxHeight = '400px',
}: OfflineDocumentListProps) {
  const [documents, setDocuments] = React.useState<CachedDocument[]>([]);
  const [storage, setStorage] = React.useState<StorageInfo>({
    usage: 0,
    quota: 0,
    percentUsed: 0,
  });
  const [isLoading, setIsLoading] = React.useState(true);
  const [isClearing, setIsClearing] = React.useState(false);

  /**
   * Load cached documents and storage info
   */
  const loadData = React.useCallback(async () => {
    setIsLoading(true);
    try {
      const [docs, storageInfo] = await Promise.all([
        getAllCachedDocuments(),
        getStorageEstimate(),
      ]);

      // Sort by cached date (newest first)
      docs.sort((a, b) => b.cachedAt - a.cachedAt);

      setDocuments(docs);
      setStorage(storageInfo);
    } catch (error) {
      logger.error('[OfflineDocumentList] Fehler beim Laden', { error });
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * Clear expired documents
   */
  const handleClearExpired = React.useCallback(async () => {
    setIsClearing(true);
    try {
      const count = await clearExpiredDocuments();
      logger.info('[OfflineDocumentList] Abgelaufene Dokumente entfernt', { count });
      await loadData();
    } catch (error) {
      logger.error('[OfflineDocumentList] Fehler beim Bereinigen', { error });
    } finally {
      setIsClearing(false);
    }
  }, [loadData]);

  /**
   * Initial load
   */
  React.useEffect(() => {
    loadData();
  }, [loadData]);

  return (
    <Card className={cn('', className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-lg flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Offline verfügbar
            </CardTitle>
            <CardDescription>
              {documents.length} {documents.length === 1 ? 'Dokument' : 'Dokumente'} gecached
            </CardDescription>
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={loadData}
              disabled={isLoading}
            >
              <RefreshCw className={cn('h-4 w-4', isLoading && 'animate-spin')} />
            </Button>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={isClearing || documents.length === 0}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Cache bereinigen?</AlertDialogTitle>
                  <AlertDialogDescription>
                    Abgelaufene Dokumente werden aus dem Offline-Speicher entfernt.
                    Aktuelle Dokumente bleiben erhalten.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Abbrechen</AlertDialogCancel>
                  <AlertDialogAction onClick={handleClearExpired}>
                    Bereinigen
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </div>
      </CardHeader>

      <CardContent className="pt-0">
        {/* Storage usage */}
        <div className="mb-4 p-3 bg-muted rounded-lg">
          <div className="flex items-center gap-2 mb-2">
            <HardDrive className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium">Speichernutzung</span>
          </div>
          <Progress value={storage.percentUsed} className="h-2 mb-1" />
          <p className="text-xs text-muted-foreground">
            {formatBytes(storage.usage)} von {formatBytes(storage.quota)} verwendet
            ({storage.percentUsed.toFixed(1)}%)
          </p>
        </div>

        {/* Document list */}
        {isLoading ? (
          <div className="text-center py-8 text-muted-foreground">
            Lade Dokumente...
          </div>
        ) : documents.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <FileText className="h-12 w-12 mx-auto mb-2 opacity-50" />
            <p>Keine Dokumente offline verfügbar</p>
            <p className="text-sm mt-1">
              Öffnen Sie Dokumente online, um sie zu cachen
            </p>
          </div>
        ) : (
          <ScrollArea style={{ maxHeight }}>
            <div className="space-y-2">
              {documents.map((doc) => (
                <div
                  key={doc.id}
                  className={cn(
                    'p-3 rounded-lg border cursor-pointer transition-colors',
                    'hover:bg-accent hover:text-accent-foreground'
                  )}
                  onClick={() => onSelectDocument?.(doc)}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <p className="font-medium truncate">{doc.title}</p>
                      {doc.extractedText && (
                        <p className="text-sm text-muted-foreground truncate mt-1">
                          {doc.extractedText.slice(0, 100)}...
                        </p>
                      )}
                    </div>
                    {doc.thumbnailUrl && (
                      <img
                        src={doc.thumbnailUrl}
                        alt=""
                        className="w-12 h-12 object-cover rounded shrink-0"
                      />
                    )}
                  </div>
                  <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <Calendar className="h-3 w-3" />
                      {formatDate(doc.cachedAt)}
                    </span>
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      Gültig: {getTimeUntilExpiry(doc.expiresAt)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
}

export default OfflineDocumentList;
