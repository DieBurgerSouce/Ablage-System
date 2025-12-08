import { useEffect, useState } from 'react';
import { Loader2, Sparkles, FileSearch, CheckCircle2 } from 'lucide-react';
import { Progress } from '@/components/ui/progress';

interface AnalysisStepProps {
    onComplete: () => void;
}

export function AnalysisStep({ onComplete }: AnalysisStepProps) {
    const [progress, setProgress] = useState(0);
    const [status, setStatus] = useState('Initialisiere Smart Analysis...');

    useEffect(() => {
        const steps = [
            { p: 10, msg: 'Dokumente werden gescannt...' },
            { p: 30, msg: 'Identifiziere Dokumententypen...' },
            { p: 60, msg: 'Prüfe auf Zusammenhänge...' },
            { p: 80, msg: 'Validiere Qualität...' },
            { p: 100, msg: 'Analyse abgeschlossen!' }
        ];

        let currentStep = 0;

        const interval = setInterval(() => {
            if (currentStep >= steps.length) {
                clearInterval(interval);
                setTimeout(onComplete, 500);
                return;
            }

            const step = steps[currentStep];
            setProgress(step.p);
            setStatus(step.msg);
            currentStep++;
        }, 800); // Simulate processing time

        return () => clearInterval(interval);
    }, [onComplete]);

    return (
        <div className="flex flex-col items-center justify-center min-h-[400px] space-y-8 animate-in fade-in duration-700">
            <div className="relative">
                <div className="absolute inset-0 bg-primary/20 blur-xl rounded-full animate-pulse" />
                <div className="relative bg-background p-6 rounded-full border-2 border-primary/20 shadow-xl">
                    <Sparkles className="w-12 h-12 text-primary animate-spin-slow" />
                </div>
            </div>

            <div className="text-center space-y-2 max-w-md">
                <h3 className="text-2xl font-semibold tracking-tight">Smart Analysis läuft</h3>
                <p className="text-muted-foreground min-h-[1.5rem] transition-all duration-300">
                    {status}
                </p>
            </div>

            <div className="w-full max-w-md space-y-2">
                <Progress value={progress} className="h-2" />
                <div className="flex justify-between text-xs text-muted-foreground">
                    <span>Start</span>
                    <span>{progress}%</span>
                </div>
            </div>

            <div className="grid grid-cols-3 gap-4 w-full max-w-lg mt-8 opacity-50">
                <div className="flex flex-col items-center gap-2 p-4 rounded-lg bg-muted/30">
                    <FileSearch className="w-5 h-5" />
                    <span className="text-xs font-medium">Klassifizierung</span>
                </div>
                <div className="flex flex-col items-center gap-2 p-4 rounded-lg bg-muted/30">
                    <Loader2 className="w-5 h-5 animate-spin" />
                    <span className="text-xs font-medium">Beziehungen</span>
                </div>
                <div className="flex flex-col items-center gap-2 p-4 rounded-lg bg-muted/30">
                    <CheckCircle2 className="w-5 h-5" />
                    <span className="text-xs font-medium">Validierung</span>
                </div>
            </div>
        </div>
    );
}
