import { useState } from 'react';
import type { UploadState } from '../types';
import { TuneSelectionStep } from '../steps/TuneSelectionStep';
import { UploadStep } from '../steps/UploadStep';
import { AnalysisStep } from '../steps/AnalysisStep';
import { ReviewStep } from '../steps/ReviewStep';
import { analyzeDocuments } from '@/lib/api/smart-analysis';
import { useNavigate } from '@tanstack/react-router';

export function UploadWizard() {
    const navigate = useNavigate();
    const [state, setState] = useState<UploadState>({
        step: 'tune-selection',
        selectedTuneId: null,
        files: [],
        analysisResults: [],
        groups: []
    });

    const handleTuneSelect = (tuneId: string) => {
        setState(prev => ({ ...prev, selectedTuneId: tuneId, step: 'upload' }));
    };

    const handleFilesAdd = (newFiles: File[]) => {
        setState(prev => ({ ...prev, files: [...prev.files, ...newFiles] }));
    };

    const handleStartAnalysis = async () => {
        setState(prev => ({ ...prev, step: 'analysis' }));
        // The AnalysisStep component handles the visual progress
        // We trigger the actual (mock) API call here
        try {
            const results = await analyzeDocuments(state.files, state.selectedTuneId!);
            setState(prev => ({ ...prev, analysisResults: results }));
        } catch (error) {
            console.error("Fehler bei der Analyse", error);
            setState(prev => ({ ...prev, step: 'upload' }));
        }
    };

    const handleAnalysisComplete = () => {
        setState(prev => ({ ...prev, step: 'review' }));
    };

    const handleUpdateTune = (fileId: string, tuneId: string) => {
        setState(prev => ({
            ...prev,
            analysisResults: prev.analysisResults.map(r =>
                r.fileId === fileId ? { ...r, detectedTuneId: tuneId } : r
            )
        }));
    };

    const handleRemoveFile = (fileId: string) => {
        setState(prev => ({
            ...prev,
            files: prev.files.filter((_, i) => `file-${i}` !== fileId), // Note: fileId logic in mock is index based, this is a simplification
            analysisResults: prev.analysisResults.filter(r => r.fileId !== fileId)
        }));
    };

    const handleConfirm = () => {
        // Here we would send the final data to the backend
        console.log(`${state.analysisResults.length} Dokumente erfolgreich verarbeitet!`);
        navigate({ to: '/' });
    };

    return (
        <div className="max-w-5xl mx-auto py-8 px-4">
            {/* Progress Stepper (Simplified) */}
            <div className="flex items-center justify-center mb-12 space-x-4">
                <StepIndicator active={state.step === 'tune-selection'} completed={state.step !== 'tune-selection'} number={1} label="Tune" />
                <div className="w-12 h-px bg-border" />
                <StepIndicator active={state.step === 'upload'} completed={['analysis', 'review'].includes(state.step)} number={2} label="Upload" />
                <div className="w-12 h-px bg-border" />
                <StepIndicator active={state.step === 'analysis'} completed={state.step === 'review'} number={3} label="Analyse" />
                <div className="w-12 h-px bg-border" />
                <StepIndicator active={state.step === 'review'} completed={false} number={4} label="Review" />
            </div>

            <div className="bg-background rounded-2xl border shadow-sm p-8 min-h-[600px]">
                {state.step === 'tune-selection' && (
                    <TuneSelectionStep
                        selectedTuneId={state.selectedTuneId}
                        onSelect={handleTuneSelect}
                    />
                )}

                {state.step === 'upload' && (
                    <UploadStep
                        files={state.files}
                        onFilesAdded={handleFilesAdd}
                        onBack={() => setState(prev => ({ ...prev, step: 'tune-selection' }))}
                        onNext={handleStartAnalysis}
                    />
                )}

                {state.step === 'analysis' && (
                    <AnalysisStep onComplete={handleAnalysisComplete} />
                )}

                {state.step === 'review' && (
                    <ReviewStep
                        results={state.analysisResults}
                        onUpdateTune={handleUpdateTune}
                        onRemove={handleRemoveFile}
                        onBack={() => setState(prev => ({ ...prev, step: 'upload' }))}
                        onConfirm={handleConfirm}
                    />
                )}
            </div>
        </div>
    );
}

function StepIndicator({ active, completed, number, label }: { active: boolean, completed: boolean, number: number, label: string }) {
    return (
        <div className="flex flex-col items-center gap-2">
            <div className={`
                w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-all duration-300
                ${active ? 'bg-primary text-primary-foreground scale-110 ring-4 ring-primary/20' : ''}
                ${completed ? 'bg-primary text-primary-foreground' : ''}
                ${!active && !completed ? 'bg-muted text-muted-foreground' : ''}
            `}>
                {number}
            </div>
            <span className={`text-xs font-medium ${active ? 'text-primary' : 'text-muted-foreground'}`}>
                {label}
            </span>
        </div>
    );
}
