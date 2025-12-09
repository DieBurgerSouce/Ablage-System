import { OCRBackendSelector } from '../components/OCRBackendSelector';
import { TuneSelectionStep } from './TuneSelectionStep'; // Reusing the component logic, but we might need to adapt styling
import { UploadDropzone } from '../components/UploadDropzone';
import { Separator } from '@/components/ui/separator';

interface UnifiedUploadStepProps {
    selectedBackendId: string | null;
    onBackendSelect: (id: string) => void;
    selectedTuneId: string | null;
    onTuneSelect: (id: string) => void;
    onFilesAdded: (files: File[]) => void;
}

export function UnifiedUploadStep({
    selectedBackendId,
    onBackendSelect,
    selectedTuneId,
    onTuneSelect,
    onFilesAdded
}: UnifiedUploadStepProps) {
    return (
        <div className="space-y-12 animate-in fade-in slide-in-from-bottom-4 duration-500">
            {/* Section 1: Backend Selection */}
            <section className="space-y-4">
                <div className="flex items-center gap-4">
                    <div className="flex items-center justify-center w-8 h-8 rounded-full bg-primary text-primary-foreground font-bold text-sm">1</div>
                    <h2 className="text-xl font-semibold tracking-tight">OCR Engine wählen</h2>
                </div>
                <div className="pl-12">
                    <OCRBackendSelector
                        selectedId={selectedBackendId || ''}
                        onSelect={onBackendSelect}
                        gpuAvailable={true}
                    />
                </div>
            </section>

            <Separator />

            {/* Section 2: Tune Selection */}
            <section className="space-y-4">
                <div className="flex items-center gap-4">
                    <div className="flex items-center justify-center w-8 h-8 rounded-full bg-primary text-primary-foreground font-bold text-sm">2</div>
                    <h2 className="text-xl font-semibold tracking-tight">Kontext bestimmen</h2>
                </div>
                <div className="pl-12">
                    <TuneSelectionStep
                        selectedTuneId={selectedTuneId}
                        onSelect={onTuneSelect}
                        embedded
                    />
                </div>
            </section>

            <Separator />

            {/* Section 3: Upload */}
            <section className="space-y-4">
                <div className="flex items-center gap-4">
                    <div className="flex items-center justify-center w-8 h-8 rounded-full bg-primary text-primary-foreground font-bold text-sm">3</div>
                    <h2 className="text-xl font-semibold tracking-tight">Dokumente hochladen</h2>
                </div>
                <div className="pl-12 max-w-3xl">
                    <UploadDropzone onFilesAdd={onFilesAdded} />
                </div>
            </section>
        </div>
    );
}
