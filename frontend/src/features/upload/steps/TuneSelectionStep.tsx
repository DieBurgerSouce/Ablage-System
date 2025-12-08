import { AVAILABLE_TUNES } from '@/lib/api/smart-analysis';
import { cn } from '@/lib/utils';
import { Receipt, Scale, Mail, Wrench, Check } from 'lucide-react';

interface TuneSelectionStepProps {
    selectedTuneId: string | null;
    onSelect: (tuneId: string) => void;
}

const iconMap: Record<string, any> = {
    Receipt,
    Scale,
    Mail,
    Wrench
};

export function TuneSelectionStep({ selectedTuneId, onSelect }: TuneSelectionStepProps) {
    return (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="text-center space-y-2">
                <h2 className="text-2xl font-semibold tracking-tight">Wählen Sie einen Tune</h2>
                <p className="text-muted-foreground">
                    Bestimmen Sie den Kontext für die intelligente Analyse Ihrer Dokumente.
                </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-4xl mx-auto">
                {AVAILABLE_TUNES.map((tune) => {
                    const Icon = iconMap[tune.icon] || Mail;
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
                                <h3 className={cn("font-semibold", isSelected ? "text-primary" : "text-foreground")}>
                                    {tune.name}
                                </h3>
                                <p className="text-sm text-muted-foreground leading-relaxed">
                                    {tune.description}
                                </p>
                            </div>

                            {isSelected && (
                                <div className="absolute top-4 right-4 text-primary animate-in zoom-in duration-200">
                                    <Check className="w-5 h-5" />
                                </div>
                            )}
                        </button>
                    );
                })}
            </div>
        </div>
    );
}
