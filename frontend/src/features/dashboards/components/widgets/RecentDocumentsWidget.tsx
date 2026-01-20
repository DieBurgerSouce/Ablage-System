/**
 * Recent Documents Widget
 *
 * Zeigt die neuesten Dokumente an
 */

import { useQuery } from '@tanstack/react-query';
import { WidgetWrapper } from './WidgetWrapper';
import { FileText, Calendar } from 'lucide-react';
import type { Widget } from '../../types';
import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';
import { Badge } from '@/components/ui/badge';

interface RecentDocumentsWidgetProps {
  widget: Widget;
  onRemove?: () => void;
  onSettings?: () => void;
  isEditing?: boolean;
}

interface Document {
  id: string;
  filename: string;
  document_type: string;
  created_at: string;
  ocr_status: string;
}

export function RecentDocumentsWidget({
  widget,
  onRemove,
  onSettings,
  isEditing,
}: RecentDocumentsWidgetProps) {
  const limit = widget.config?.limit ?? 5;

  const { data, isLoading } = useQuery<Document[]>({
    queryKey: ['widget-data', 'recent-documents', widget.id, limit],
    queryFn: async () => {
      const response = await fetch(
        `/api/v1/documents?limit=${limit}&sort=-created_at`,
        {
          credentials: 'include',
        }
      );
      if (!response.ok) throw new Error('Fehler beim Laden der Dokumente');
      const result = await response.json();
      return result.documents ?? [];
    },
  });

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'bg-green-500';
      case 'processing':
        return 'bg-blue-500';
      case 'failed':
        return 'bg-red-500';
      default:
        return 'bg-gray-500';
    }
  };

  return (
    <WidgetWrapper
      title={widget.title}
      onRemove={onRemove}
      onSettings={onSettings}
      isEditing={isEditing}
    >
      {isLoading ? (
        <div className="flex items-center justify-center h-full">
          <div className="text-sm text-muted-foreground">Lädt...</div>
        </div>
      ) : data && data.length > 0 ? (
        <div className="space-y-2">
          {data.map((doc) => (
            <div
              key={doc.id}
              className="flex items-start gap-3 p-2 rounded-lg hover:bg-muted/50 transition-colors cursor-pointer"
            >
              <div className="p-2 rounded bg-primary/10">
                <FileText className="h-4 w-4 text-primary" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-medium text-sm truncate">
                  {doc.filename}
                </div>
                <div className="flex items-center gap-2 mt-1">
                  {doc.document_type && (
                    <Badge variant="secondary" className="text-xs">
                      {doc.document_type}
                    </Badge>
                  )}
                  <div className="flex items-center gap-1 text-xs text-muted-foreground">
                    <Calendar className="h-3 w-3" />
                    {formatDistanceToNow(new Date(doc.created_at), {
                      addSuffix: true,
                      locale: de,
                    })}
                  </div>
                </div>
              </div>
              <div
                className={`h-2 w-2 rounded-full ${getStatusColor(
                  doc.ocr_status
                )}`}
                title={doc.ocr_status}
              />
            </div>
          ))}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center h-full text-center p-4">
          <FileText className="h-8 w-8 text-muted-foreground mb-2" />
          <div className="text-sm text-muted-foreground">
            Noch keine Dokumente vorhanden
          </div>
        </div>
      )}
    </WidgetWrapper>
  );
}
