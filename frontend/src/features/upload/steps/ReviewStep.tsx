import type { SmartAnalysisResult } from '../types';
import { ReviewDashboard } from '../components/ReviewDashboard';
import { DocumentList } from '../components/DocumentList';
import { Button } from '@/components/ui/button';
import { ArrowLeft, CheckCircle } from 'lucide-react';

interface ReviewStepProps {
    results: SmartAnalysisResult[];
    onUpdateTune: (fileId: string, tuneId: string) => void;
    onUpdateBackend: (fileId: string, backendId: string) => void;
    onRemove: (fileId: string) => void;
    onBack: () => void;
    onConfirm: () => void;
}

export function ReviewStep({ results, onUpdateTune, onUpdateBackend, onRemove, onBack, onConfirm }: ReviewStepProps) {
    return (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-semibold tracking-tight">Ergebnisse überprüfen</h2>
                    <p className="text-muted-foreground">
                        Bitte bestätigen Sie die automatische Analyse vor der Verarbeitung.
                    </p>
                </div>
            </div>

            <ReviewDashboard results={results} />

            <div className="bg-muted/10 rounded-xl border p-6" data-tour="ocr-result">
                <DocumentList
                    results={results}
                    onUpdateTune={onUpdateTune}
                    onUpdateBackend={onUpdateBackend}
                    onRemove={onRemove}
                />
            </div>

            <div className="flex justify-between pt-8">
                <Button variant="ghost" onClick={onBack} className="gap-2">
                    <ArrowLeft className="w-4 h-4" />
                    Zurück
                </Button>
                <Button
                    onClick={onConfirm}
                    size="lg"
                    className="gap-2 bg-emerald-600 hover:bg-emerald-700 text-white"
                    data-tour="process-button"
                >
                    <CheckCircle className="w-4 h-4" />
                    Verarbeitung starten
                </Button>
            </div>
        </div>
    );
}
