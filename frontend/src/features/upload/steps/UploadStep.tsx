import { UploadDropzone } from '../components/UploadDropzone';
import { Button } from '@/components/ui/button';
import { ArrowLeft, ArrowRight } from 'lucide-react';

interface UploadStepProps {
    onFilesAdded: (files: File[]) => void;
    onBack: () => void;
    onNext: () => void;
    files: File[];
}

export function UploadStep({ onFilesAdded, onBack, onNext, files }: UploadStepProps) {
    return (
        <div className="space-y-6 animate-in fade-in slide-in-from-right-8 duration-500">
            <div className="text-center space-y-2">
                <h2 className="text-2xl font-semibold tracking-tight">Dokumente hochladen</h2>
                <p className="text-muted-foreground">
                    Ziehen Sie Ihre Dateien hierher oder klicken Sie zum Auswählen.
                </p>
            </div>

            <div className="max-w-3xl mx-auto">
                <UploadDropzone onFilesAdd={onFilesAdded} />

                {files.length > 0 && (
                    <div className="mt-6 bg-muted/30 rounded-lg p-4 border border-border/50">
                        <div className="flex items-center justify-between mb-2">
                            <span className="font-medium text-sm">Ausgewählte Dateien ({files.length})</span>
                            <span className="text-xs text-muted-foreground">
                                {Math.round(files.reduce((acc, f) => acc + f.size, 0) / 1024 / 1024 * 100) / 100} MB gesamt
                            </span>
                        </div>
                        <div className="max-h-40 overflow-y-auto space-y-2 pr-2 custom-scrollbar">
                            {files.map((file, idx) => (
                                <div key={idx} className="flex items-center justify-between text-sm p-2 bg-background rounded border border-border/50">
                                    <span className="truncate max-w-[300px]">{file.name}</span>
                                    <span className="text-muted-foreground text-xs">
                                        {Math.round(file.size / 1024)} KB
                                    </span>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>

            <div className="flex justify-between max-w-3xl mx-auto pt-8">
                <Button variant="ghost" onClick={onBack} className="gap-2">
                    <ArrowLeft className="w-4 h-4" />
                    Zurück
                </Button>
                <Button
                    onClick={onNext}
                    disabled={files.length === 0}
                    className="gap-2"
                >
                    Analyse starten
                    <ArrowRight className="w-4 h-4" />
                </Button>
            </div>
        </div>
    );
}
