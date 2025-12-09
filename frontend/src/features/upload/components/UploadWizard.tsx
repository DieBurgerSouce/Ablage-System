import { useState, useEffect, useCallback } from 'react';
import type { UploadState } from '../types';
import { UnifiedUploadStep } from '../steps/UnifiedUploadStep';
import { AnalysisStep } from '../steps/AnalysisStep';
import { ReviewStep } from '../steps/ReviewStep';
import { analyzeDocuments, cleanupAnalysisResults } from '@/lib/api/smart-analysis';
import { useNavigate } from '@tanstack/react-router';

export function UploadWizard() {
    const navigate = useNavigate();
    const [state, setState] = useState<UploadState>({
        step: 'upload',
        selectedBackendId: 'deepseek-janus', // Default recommendation
        selectedTuneId: null,
        files: [],
        analysisResults: [],
        groups: []
    });

    // Cleanup blob URLs on unmount to prevent memory leaks
    useEffect(() => {
        return () => {
            cleanupAnalysisResults(state.analysisResults);
        };
    }, [state.analysisResults]);

    const handleBackendSelect = useCallback((backendId: string) => {
        setState(prev => ({ ...prev, selectedBackendId: backendId }));
    }, []);

    const handleTuneSelect = useCallback((tuneId: string) => {
        setState(prev => ({ ...prev, selectedTuneId: tuneId }));
    }, []);

    const handleFilesAdd = async (newFiles: File[]) => {
        // Validate that backend and tune are selected
        const backendId = state.selectedBackendId || 'deepseek-janus';
        const tuneId = state.selectedTuneId || 'default'; // Fallback if no tune selected

        // Immediately start analysis when files are added
        setState(prev => ({ ...prev, files: [...prev.files, ...newFiles], step: 'analysis' }));

        try {
            const results = await analyzeDocuments(newFiles, tuneId, backendId);
            setState(prev => ({ ...prev, analysisResults: results }));
        } catch {
            // Analysis failed - return to upload step
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

    const handleUpdateBackend = (fileId: string, backendId: string) => {
        setState(prev => ({
            ...prev,
            analysisResults: prev.analysisResults.map(r =>
                r.fileId === fileId ? { ...r, selectedBackendId: backendId } : r
            )
        }));
    };

    const handleRemoveFile = useCallback((fileId: string) => {
        setState(prev => {
            // Find the result to cleanup its blob URL
            const resultToRemove = prev.analysisResults.find(r => r.fileId === fileId);
            if (resultToRemove) {
                cleanupAnalysisResults([resultToRemove]);
            }

            // Filter analysisResults by fileId (UUID-based)
            // Note: files array is kept in sync by fileName matching for re-uploads
            const newAnalysisResults = prev.analysisResults.filter(r => r.fileId !== fileId);

            // Also remove any children that reference this file as parent
            const filteredResults = newAnalysisResults.filter(r => r.parentId !== fileId);

            // Remove corresponding file by matching fileName
            const removedFileName = resultToRemove?.fileName;
            const newFiles = removedFileName
                ? prev.files.filter(f => f.name !== removedFileName)
                : prev.files;

            return {
                ...prev,
                files: newFiles,
                analysisResults: filteredResults
            };
        });
    }, []);

    const handleConfirm = useCallback(() => {
        // Cleanup blob URLs before navigating away
        cleanupAnalysisResults(state.analysisResults);
        navigate({ to: '/' });
    }, [navigate, state.analysisResults]);

    return (
        <div className="max-w-7xl mx-auto py-8 px-4">
            {/* Simplified Progress Indicator */}
            <div className="flex items-center justify-center mb-12 space-x-4">
                <StepIndicator active={state.step === 'upload'} completed={['analysis', 'review'].includes(state.step)} number={1} label="Konfiguration & Upload" />
                <div className="w-12 h-px bg-border" />
                <StepIndicator active={state.step === 'analysis'} completed={state.step === 'review'} number={2} label="Smart Analyse" />
                <div className="w-12 h-px bg-border" />
                <StepIndicator active={state.step === 'review'} completed={false} number={3} label="Review & Start" />
            </div>

            <div className="bg-background rounded-2xl border shadow-sm p-8 min-h-[600px]">
                {state.step === 'upload' && (
                    <UnifiedUploadStep
                        selectedBackendId={state.selectedBackendId}
                        onBackendSelect={handleBackendSelect}
                        selectedTuneId={state.selectedTuneId}
                        onTuneSelect={handleTuneSelect}
                        onFilesAdded={handleFilesAdd}
                    />
                )}

                {state.step === 'analysis' && (
                    <AnalysisStep onComplete={handleAnalysisComplete} />
                )}

                {state.step === 'review' && (
                    <ReviewStep
                        results={state.analysisResults}
                        onUpdateTune={handleUpdateTune}
                        onUpdateBackend={handleUpdateBackend}
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
