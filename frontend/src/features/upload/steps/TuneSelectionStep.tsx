import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api/client';
import { cn } from '@/lib/utils';
import {
    Loader2, Check, FileText, Receipt, Scale, Mail, Wrench,
    Image, Book, Briefcase, CreditCard, DollarSign
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { Tune } from '../types';

// Type-safe icon mapping
const ICON_MAP: Record<string, LucideIcon> = {
    Receipt, Scale, Mail, Wrench, FileText, Image, Book, Briefcase, CreditCard, DollarSign
};

interface TuneSelectionStepProps {
    selectedTuneId: string | null;
    onSelect: (tuneId: string) => void;
    /** When true, hides the header for embedded usage in UnifiedUploadStep */
    embedded?: boolean;
}

export function TuneSelectionStep({ selectedTuneId, onSelect, embedded = false }: TuneSelectionStepProps) {
    const { data: tunes, isLoading } = useQuery({
        queryKey: ['tunes', 'active'],
        queryFn: async () => {
            const response = await apiClient.get('/tunes?active_only=true');
            return response.data as Tune[];
        }
    });

    if (isLoading) {
        return (
            <div className="flex justify-center p-8">
                <Loader2 className="animate-spin h-8 w-8 text-muted-foreground" />
            </div>
        );
    }

    return (
        <div className={cn(
            "space-y-6",
            !embedded && "animate-in fade-in slide-in-from-bottom-4 duration-500"
        )}>
            {!embedded && (
                <div className="text-center space-y-2">
                    <h2 className="text-2xl font-semibold tracking-tight">Wählen Sie einen Tune</h2>
                    <p className="text-muted-foreground">
                        Bestimmen Sie den Kontext für die intelligente Analyse Ihrer Dokumente.
                    </p>
                </div>
            )}

            <div className={cn(
                "grid grid-cols-1 md:grid-cols-2 gap-4",
                !embedded && "max-w-4xl mx-auto"
            )}>
                {tunes?.map((tune) => {
                    // Type-safe icon lookup
                    const Icon = ICON_MAP[tune.icon] || FileText;
                    const isSelected = selectedTuneId === tune.id;

                    return (
                        <button
                            key={tune.id}
                            onClick={() => onSelect(tune.id)}
                            className={cn(
                                "relative group flex items-start space-x-4 p-6 rounded-xl border-2 text-left transition-all duration-200 hover:shadow-md",
                                isSelected
                                    ? "border-primary bg-primary/5 shadow-lg scale-[1.02]"
                                    : "border-border bg-card hover:border-primary/50 hover:bg-accent/50"
                            )}
                        >
                            <div className={cn(
                                "p-3 rounded-lg transition-colors",
                                isSelected ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground group-hover:text-foreground"
                            )}>
                                <Icon className="w-6 h-6" />
                            </div>

                            <div className="flex-1 space-y-1">
                                <div className="flex items-center justify-between">
                                    <h3 className="font-semibold">{tune.name}</h3>
                                    {isSelected && (
                                        <Check className="w-5 h-5 text-primary animate-in zoom-in duration-300" />
                                    )}
                                </div>
                                <p className="text-sm text-muted-foreground leading-relaxed">
                                    {tune.description}
                                </p>
                            </div>
                        </button>
                    );
                })}
            </div>
        </div>
    );
}
