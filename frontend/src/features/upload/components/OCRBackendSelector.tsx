import { motion } from 'framer-motion';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { motionTokens } from '@/lib/motion-tokens';
import { Cpu, Zap, Languages, Sparkles } from 'lucide-react';

interface OCRBackendSelectorProps {
    selectedId: string;
    onSelect: (id: string) => void;
    gpuAvailable: boolean;
}

const backends = [
    {
        id: 'got-ocr',
        name: 'GOT-OCR 2.0',
        description: 'State-of-the-art unified OCR mit Layout-Erkennung',
        features: ['LaTeX-Formeln', 'Tabellen', 'Bounding Boxes'],
        accuracy: 98,
        languages: 25,
        recommended: true,
        gpuRequired: true,
        icon: Zap
    },
    {
        id: 'surya-docling',
        name: 'Surya + Docling',
        description: 'Multilingual OCR mit Document Understanding',
        features: ['90+ Sprachen', 'Tabellen-Extraktion'],
        accuracy: 96,
        languages: 90,
        gpuRequired: true,
        icon: Languages
    },
    {
        id: 'deepseek-janus',
        name: 'DeepSeek Janus',
        description: 'Vision-Language Model für komplexe Dokumente',
        features: ['Kontextverständnis', 'Reasoning'],
        accuracy: 94,
        languages: 12,
        gpuRequired: true,
        icon: Sparkles
    }
];

const MotionButton = motion.button;

export function OCRBackendSelector({ selectedId, onSelect, gpuAvailable }: OCRBackendSelectorProps) {
    return (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 w-full max-w-5xl">
            {backends.map((backend) => {
                const Icon = backend.icon;
                const isSelected = selectedId === backend.id;
                const isDisabled = backend.gpuRequired && !gpuAvailable;

                return (
                    <MotionButton
                        key={backend.id}
                        whileHover={!isDisabled ? { scale: 1.02, y: -2 } : {}}
                        whileTap={!isDisabled ? { scale: 0.98 } : {}}
                        animate={isSelected ? {
                            boxShadow: '0 0 0 2px var(--primary)',
                            borderColor: 'var(--primary)'
                        } : {
                            borderColor: 'var(--border)'
                        }}
                        transition={motionTokens.spring.snappy}
                        onClick={() => !isDisabled && onSelect(backend.id)}
                        disabled={isDisabled}
                        className={cn(
                            "relative text-left p-5 rounded-xl border bg-card transition-colors flex flex-col h-full glass-card",
                            isDisabled && "opacity-50 cursor-not-allowed grayscale",
                            isSelected && "bg-primary/5"
                        )}
                    >
                        {backend.recommended && (
                            <Badge className="absolute top-3 right-3 bg-primary text-primary-foreground hover:bg-primary">
                                Empfohlen
                            </Badge>
                        )}

                        <div className="mb-4 p-3 rounded-lg bg-muted/50 w-fit">
                            <Icon className="w-6 h-6 text-primary" />
                        </div>

                        <div className="space-y-2 flex-1">
                            <h3 className="font-display font-semibold text-lg leading-tight">
                                {backend.name}
                            </h3>
                            <p className="text-sm text-muted-foreground leading-relaxed">
                                {backend.description}
                            </p>
                        </div>

                        <div className="mt-6 pt-4 border-t grid grid-cols-2 gap-4">
                            <div>
                                <div className="text-2xl font-display font-bold text-foreground">
                                    {backend.accuracy}%
                                </div>
                                <div className="text-xs text-muted-foreground font-medium uppercase tracking-wider">
                                    Genauigkeit
                                </div>
                            </div>
                            <div>
                                <div className="text-2xl font-display font-bold text-foreground">
                                    {backend.languages}
                                </div>
                                <div className="text-xs text-muted-foreground font-medium uppercase tracking-wider">
                                    Sprachen
                                </div>
                            </div>
                        </div>

                        {backend.gpuRequired && (
                            <div className="mt-4 flex items-center gap-1.5 text-xs text-muted-foreground bg-muted/30 p-2 rounded-md">
                                <Cpu className="w-3.5 h-3.5" />
                                <span>GPU erforderlich</span>
                            </div>
                        )}
                    </MotionButton>
                );
            })}
        </div>
    );
}
