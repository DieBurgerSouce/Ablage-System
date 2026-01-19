/**
 * Company Selector Component
 *
 * Multi-Select fuer Firmenfilterung im Holding-Dashboard.
 */

import { useState } from 'react';
import { Check, ChevronsUpDown, Building2 } from 'lucide-react';
import { cn } from '@/lib/utils';
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
import { Badge } from '@/components/ui/badge';
import type { CompanySummary } from '../api/holding-api';

interface CompanySelectorProps {
  companies: CompanySummary[];
  selectedIds: string[];
  onSelectionChange: (ids: string[]) => void;
}

export function CompanySelector({
  companies,
  selectedIds,
  onSelectionChange,
}: CompanySelectorProps) {
  const [open, setOpen] = useState(false);

  const toggleCompany = (companyId: string) => {
    if (selectedIds.includes(companyId)) {
      onSelectionChange(selectedIds.filter((id) => id !== companyId));
    } else {
      onSelectionChange([...selectedIds, companyId]);
    }
  };

  const selectAll = () => {
    onSelectionChange(companies.map((c) => c.id));
  };

  const clearSelection = () => {
    onSelectionChange([]);
  };

  const selectedCompanies = companies.filter((c) => selectedIds.includes(c.id));
  const allSelected = selectedIds.length === companies.length;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-[300px] justify-between"
        >
          <div className="flex items-center gap-2 truncate">
            <Building2 className="h-4 w-4 shrink-0" />
            {selectedIds.length === 0 ? (
              <span className="text-muted-foreground">Alle Firmen</span>
            ) : selectedIds.length === companies.length ? (
              <span>Alle Firmen ({companies.length})</span>
            ) : (
              <span>
                {selectedIds.length} von {companies.length} Firmen
              </span>
            )}
          </div>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[300px] p-0">
        <Command>
          <CommandInput placeholder="Firma suchen..." />
          <CommandList>
            <CommandEmpty>Keine Firma gefunden.</CommandEmpty>
            <CommandGroup>
              {/* Select All / Clear */}
              <div className="flex gap-2 p-2 border-b">
                <Button
                  variant="ghost"
                  size="sm"
                  className="flex-1 text-xs"
                  onClick={selectAll}
                  disabled={allSelected}
                >
                  Alle auswaehlen
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="flex-1 text-xs"
                  onClick={clearSelection}
                  disabled={selectedIds.length === 0}
                >
                  Auswahl loeschen
                </Button>
              </div>

              {/* Company List */}
              {companies.map((company) => (
                <CommandItem
                  key={company.id}
                  value={company.name}
                  onSelect={() => toggleCompany(company.id)}
                >
                  <Check
                    className={cn(
                      'mr-2 h-4 w-4',
                      selectedIds.includes(company.id) ? 'opacity-100' : 'opacity-0'
                    )}
                  />
                  <div className="flex flex-col flex-1 min-w-0">
                    <span className="truncate">{company.name}</span>
                    {company.short_name && (
                      <span className="text-xs text-muted-foreground truncate">
                        {company.short_name}
                      </span>
                    )}
                  </div>
                  <Badge variant="outline" className="ml-2 shrink-0">
                    {company.subscription_tier}
                  </Badge>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
