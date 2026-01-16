/**
 * CompanySwitcher - Multi-Mandanten Firmenauswahl
 *
 * Ermoeglicht das Wechseln zwischen Firmen in einer Multi-Tenant-Umgebung.
 * Wird im Header angezeigt und zeigt die aktuelle Firma + Dropdown fuer Wechsel.
 *
 * Features:
 * - Zeigt aktuelle Firma mit Kurzname
 * - Dropdown mit allen verfuegbaren Firmen
 * - Ladeindikator waehrend Wechsel
 * - Unterstuetzt alle 4 Display-Modi (Dark, Light, Whitescreen, Blackscreen)
 */

import { Building2, ChevronDown, Check, Loader2 } from 'lucide-react';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { useCompany } from '@/context/CompanyContext';
import { cn } from '@/lib/utils';
import { logger } from '@/lib/logger';

interface CompanySwitcherProps {
    /** Zusaetzliche CSS-Klassen */
    className?: string;
    /** Kompakte Darstellung (nur Icon auf Mobile) */
    compact?: boolean;
}

export function CompanySwitcher({ className, compact = false }: CompanySwitcherProps) {
    const {
        currentCompany,
        companies,
        switchCompany,
        isLoading,
        hasMultipleCompanies,
    } = useCompany();

    // Keine Firma oder nur eine Firma -> Nichts anzeigen oder einfache Anzeige
    if (!currentCompany) {
        return null;
    }

    // Bei nur einer Firma: Einfache Anzeige ohne Dropdown
    if (!hasMultipleCompanies) {
        return (
            <div
                className={cn(
                    'flex items-center gap-2 px-3 py-1.5 rounded-md',
                    'text-sm text-muted-foreground',
                    className
                )}
            >
                <Building2 className="h-4 w-4" />
                <span className={cn(compact && 'hidden sm:inline')}>
                    {currentCompany.name}
                </span>
            </div>
        );
    }

    // Firmen-Kurzname oder ersten 3 Buchstaben
    const getShortName = (company: typeof currentCompany) => {
        if (!company) return '';
        // Nutze short_name falls vorhanden (aus Backend Company Model)
        const name = company.name;
        // Nimm erste 3 Buchstaben oder Initialen
        if (name.length <= 3) return name;
        // Bei Firmennamen mit Leerzeichen: Initialen
        const words = name.split(/\s+/);
        if (words.length >= 2) {
            return words.map(w => w[0]).join('').toUpperCase().substring(0, 3);
        }
        return name.substring(0, 3).toUpperCase();
    };

    const handleSwitch = async (companyId: string) => {
        if (companyId === currentCompany?.id) return;
        try {
            await switchCompany(companyId);
        } catch (error) {
            // Fehler wird im Context behandelt
            logger.error('Firma wechseln fehlgeschlagen', error);
        }
    };

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button
                    variant="ghost"
                    size="sm"
                    className={cn(
                        'flex items-center gap-2 px-2 sm:px-3',
                        'hover:bg-accent hover:text-accent-foreground',
                        'focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
                        className
                    )}
                    disabled={isLoading}
                    aria-label={`Aktuelle Firma: ${currentCompany.name}. Klicken um Firma zu wechseln.`}
                >
                    {isLoading ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                        <Building2 className="h-4 w-4" />
                    )}

                    {/* Firmenname - versteckt auf sehr kleinen Bildschirmen wenn compact */}
                    <span className={cn(
                        'font-medium truncate max-w-[120px] sm:max-w-[180px]',
                        compact && 'hidden xs:inline'
                    )}>
                        {compact ? getShortName(currentCompany) : currentCompany.name}
                    </span>

                    <ChevronDown className="h-3 w-3 opacity-50" />
                </Button>
            </DropdownMenuTrigger>

            <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuLabel className="text-xs text-muted-foreground font-normal">
                    Firma wechseln
                </DropdownMenuLabel>
                <DropdownMenuSeparator />

                {companies.map((company) => (
                    <DropdownMenuItem
                        key={company.id}
                        onClick={() => handleSwitch(company.id)}
                        className={cn(
                            'flex items-center justify-between cursor-pointer',
                            company.id === currentCompany.id && 'bg-accent/50'
                        )}
                        disabled={isLoading}
                    >
                        <div className="flex items-center gap-2 min-w-0">
                            <Building2 className="h-4 w-4 flex-shrink-0" />
                            <span className="truncate">{company.name}</span>
                        </div>

                        {company.id === currentCompany.id && (
                            <Check className="h-4 w-4 text-primary flex-shrink-0" />
                        )}
                    </DropdownMenuItem>
                ))}
            </DropdownMenuContent>
        </DropdownMenu>
    );
}

export default CompanySwitcher;
