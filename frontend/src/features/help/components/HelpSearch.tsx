/**
 * Help Search - Volltextsuche für Hilfe-Artikel
 */

import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Search } from 'lucide-react';
import { useDebounce } from '@/hooks/use-debounce';
import { useSearchHelp } from '../hooks/useHelp';
import { HELP_CATEGORY_LABELS } from '../types';

interface HelpSearchProps {
  onSelectArticle?: (articleId: string) => void;
}

export function HelpSearch({ onSelectArticle }: HelpSearchProps) {
  const [open, setOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const debouncedQuery = useDebounce(searchQuery, 300);

  const { data: results = [], isLoading } = useSearchHelp(debouncedQuery);

  const handleSelect = (articleId: string) => {
    setOpen(false);
    setSearchQuery('');
    onSelectArticle?.(articleId);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-start text-muted-foreground"
        >
          <Search className="h-4 w-4 mr-2" />
          Hilfe durchsuchen...
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[400px] p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput
            placeholder="Artikel durchsuchen..."
            value={searchQuery}
            onValueChange={setSearchQuery}
          />
          <CommandList>
            {isLoading ? (
              <div className="py-6 text-center text-sm text-muted-foreground">
                Suche läuft...
              </div>
            ) : results.length === 0 && debouncedQuery.length >= 3 ? (
              <CommandEmpty>Keine Artikel gefunden</CommandEmpty>
            ) : results.length === 0 ? (
              <div className="py-6 text-center text-sm text-muted-foreground">
                Geben Sie mindestens 3 Zeichen ein
              </div>
            ) : (
              <CommandGroup heading="Suchergebnisse">
                {results.map((result) => (
                  <CommandItem
                    key={result.article.id}
                    value={result.article.id}
                    onSelect={handleSelect}
                    className="flex flex-col items-start gap-2 py-3"
                  >
                    <div className="flex items-start justify-between w-full gap-2">
                      <span className="font-medium">
                        {result.article.title}
                      </span>
                      <Badge variant="secondary" className="text-xs">
                        {HELP_CATEGORY_LABELS[result.article.category]}
                      </Badge>
                    </div>
                    {result.highlight && (
                      <span
                        className="text-sm text-muted-foreground line-clamp-2"
                        dangerouslySetInnerHTML={{ __html: result.highlight }}
                      />
                    )}
                    <div className="flex gap-1 flex-wrap">
                      {result.article.tags.slice(0, 3).map((tag) => (
                        <Badge
                          key={tag}
                          variant="outline"
                          className="text-xs"
                        >
                          {tag}
                        </Badge>
                      ))}
                    </div>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

/**
 * Compact Search - Kleinere Variante für Sidebars
 */
export function CompactHelpSearch({ onSelectArticle }: HelpSearchProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const debouncedQuery = useDebounce(searchQuery, 300);

  const { data: results = [], isLoading } = useSearchHelp(debouncedQuery);

  const handleSelect = (articleId: string) => {
    setSearchQuery('');
    onSelectArticle?.(articleId);
  };

  return (
    <div className="space-y-2">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <input
          type="text"
          placeholder="Hilfe durchsuchen..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full pl-9 pr-3 py-2 text-sm rounded-md border border-input bg-background"
        />
      </div>

      {isLoading && debouncedQuery.length >= 3 && (
        <div className="text-xs text-center text-muted-foreground py-2">
          Suche läuft...
        </div>
      )}

      {results.length > 0 && (
        <div className="space-y-1 max-h-80 overflow-y-auto">
          {results.map((result) => (
            <button
              key={result.article.id}
              onClick={() => handleSelect(result.article.id)}
              className="w-full text-left p-2 rounded-md hover:bg-muted transition-colors"
            >
              <div className="font-medium text-sm">{result.article.title}</div>
              {result.highlight && (
                <div
                  className="text-xs text-muted-foreground line-clamp-1 mt-1"
                  dangerouslySetInnerHTML={{ __html: result.highlight }}
                />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
