/**
 * DocumentSearchSelect - Dokument-Suche und -Auswahl via Combobox.
 *
 * Durchsucht vorhandene Dokumente per debounced Input und zeigt
 * Ergebnisse in einem Popover-Dropdown an. Ausgewaehltes Dokument
 * wird als Chip angezeigt.
 */

import { useState, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api/client';
import { Button } from '@/components/ui/button';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import { Badge } from '@/components/ui/badge';
import { FileText, X, ChevronsUpDown } from 'lucide-react';
import { useDebounce } from '@/hooks/use-debounce';

interface DocumentOption {
  id: string;
  filename: string;
  document_type: string | null;
  upload_date: string | null;
}

interface DocumentSearchSelectProps {
  label: string;
  selectedDocument: DocumentOption | null;
  onSelect: (doc: DocumentOption | null) => void;
}

export function DocumentSearchSelect({
  label,
  selectedDocument,
  onSelect,
}: DocumentSearchSelectProps) {
  const [open, setOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const debouncedSearch = useDebounce(searchTerm, 300);

  const { data: documents, isLoading } = useQuery({
    queryKey: ['document-search', debouncedSearch],
    queryFn: async () => {
      const params: Record<string, string> = {
        per_page: '10',
        page: '1',
      };
      if (debouncedSearch) {
        params.search = debouncedSearch;
      }
      const response = await apiClient.get<{
        documents: DocumentOption[];
        total: number;
      }>('/documents', { params });
      return response.data.documents;
    },
    enabled: open,
    staleTime: 30_000,
  });

  const handleSelect = useCallback(
    (doc: DocumentOption) => {
      onSelect(doc);
      setOpen(false);
      setSearchTerm('');
    },
    [onSelect]
  );

  if (selectedDocument) {
    return (
      <div className="space-y-1.5">
        <span className="text-sm font-medium">{label}</span>
        <div className="flex items-center gap-2 p-2 rounded-lg border bg-muted/30">
          <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="text-sm truncate flex-1">{selectedDocument.filename}</span>
          {selectedDocument.document_type && (
            <Badge variant="secondary" className="text-[10px] shrink-0">
              {selectedDocument.document_type}
            </Badge>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0 shrink-0"
            onClick={() => onSelect(null)}
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      <span className="text-sm font-medium">{label}</span>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            role="combobox"
            aria-expanded={open}
            className="w-full justify-between font-normal text-muted-foreground"
          >
            Dokument auswaehlen...
            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
          <Command shouldFilter={false}>
            <CommandInput
              placeholder="Dokument suchen..."
              value={searchTerm}
              onValueChange={setSearchTerm}
            />
            <CommandList>
              <CommandEmpty>
                {isLoading ? 'Suche...' : 'Keine Dokumente gefunden.'}
              </CommandEmpty>
              <CommandGroup>
                {documents?.map((doc) => (
                  <CommandItem
                    key={doc.id}
                    value={doc.id}
                    onSelect={() => handleSelect(doc)}
                    className="flex items-center gap-2"
                  >
                    <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm truncate">{doc.filename}</p>
                      <div className="flex items-center gap-2">
                        {doc.document_type && (
                          <span className="text-[10px] text-muted-foreground">
                            {doc.document_type}
                          </span>
                        )}
                        {doc.upload_date && (
                          <span className="text-[10px] text-muted-foreground">
                            {new Date(doc.upload_date).toLocaleDateString('de-DE')}
                          </span>
                        )}
                      </div>
                    </div>
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  );
}
