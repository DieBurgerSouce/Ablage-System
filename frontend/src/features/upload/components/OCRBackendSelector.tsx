import { motion } from 'framer-motion';
import { Badge } from "@/components/ui/badge";

const backends = [
    {
        id: 'got-ocr',
        name: 'GOT-OCR 2.0',
        description: 'State-of-the-art unified OCR mit Layout-Erkennung',
        features: ['LaTeX-Formeln', 'Tabellen', 'Bounding Boxes'],
        accuracy: 98,
        languages: 25,
        recommended: true,
        gpuRequired: true
    },
    {
        id: 'surya-docling',
        name: 'Surya + Docling',
        description: 'Multilingual OCR mit Document Understanding',
        features: ['90+ Sprachen', 'Tabellen-Extraktion'],
        accuracy: 96,
        languages: 90,
        gpuRequired: true
    },
    {
        id: 'deepseek-janus',
        name: 'DeepSeek Janus',
        description: 'Vision-Language Model für komplexe Dokumente',
        features: ['Kontextverständnis', 'Reasoning'],
        accuracy: 94,
        gpuRequired: true
    }
];

interface OCRBackendSelectorProps {
    selectedId: string;
    onSelect: (id: string) => void;
    gpuAvailable: boolean;
}

export function OCRBackendSelector({ selectedId, onSelect, gpuAvailable }: OCRBackendSelectorProps) {
    return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {backends.map((backend) => (
                <motion.button
                    key={backend.id}
                    whileHover={{ scale: 1.02 }}
                    animate={selectedId === backend.id ? { boxShadow: '0 0 0 2px var(--primary)' } : {}}
                    onClick={() => onSelect(backend.id)}
                    disabled={backend.gpuRequired && !gpuAvailable}
                    className="relative text-left p-4 rounded-xl border bg-card hover:bg-accent/5 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                    {backend.recommended && <Badge className="absolute top-3 right-3">Empfohlen</Badge>}
                    <div className="pt-2 space-y-3">
                        <h3 className="font-semibold text-lg">{backend.name}</h3>
                        <p className="text-sm text-muted-foreground min-h-[40px]">{backend.description}</p>
                        <div className="flex flex-wrap gap-2">
                            {backend.features.slice(0, 2).map(f => (
                                <Badge key={f} variant="secondary" className="text-[10px]">{f}</Badge>
                            ))}
                        </div>
                        <div className="grid grid-cols-2 gap-2 text-center mt-4">
                            <div className="p-2 rounded-lg bg-muted/50">
                                <div className="text-lg font-bold text-primary">{backend.accuracy}%</div>
                                <div className="text-xs text-muted-foreground">Genauigkeit</div>
                            </div>
                            <div className="p-2 rounded-lg bg-muted/50">
                                <div className="text-lg font-bold text-primary">{backend.languages}</div>
                                <div className="text-xs text-muted-foreground">Sprachen</div>
                            </div>
                        </div>
                    </div>
                </motion.button>
            ))}
        </div>
    );
}
