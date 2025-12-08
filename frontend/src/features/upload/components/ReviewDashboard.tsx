import type { SmartAnalysisResult } from '../types';
import { CheckCircle2, AlertTriangle, HelpCircle } from 'lucide-react';

interface ReviewDashboardProps {
    results: SmartAnalysisResult[];
}

export function ReviewDashboard({ results }: ReviewDashboardProps) {
    const highConfidence = results.filter(r => r.confidence === 'high').length;
    const mediumConfidence = results.filter(r => r.confidence === 'medium').length;
    const lowConfidence = results.filter(r => r.confidence === 'low').length;

    return (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
            <div className="bg-card border rounded-xl p-4 flex items-center space-x-4 shadow-sm">
                <div className="p-3 bg-emerald-500/10 text-emerald-600 rounded-full">
                    <CheckCircle2 className="w-6 h-6" />
                </div>
                <div>
                    <p className="text-sm text-muted-foreground">Bereit zur Verarbeitung</p>
                    <p className="text-2xl font-bold">{highConfidence}</p>
                </div>
            </div>

            <div className="bg-card border rounded-xl p-4 flex items-center space-x-4 shadow-sm">
                <div className="p-3 bg-amber-500/10 text-amber-600 rounded-full">
                    <AlertTriangle className="w-6 h-6" />
                </div>
                <div>
                    <p className="text-sm text-muted-foreground">Prüfung empfohlen</p>
                    <p className="text-2xl font-bold">{mediumConfidence}</p>
                </div>
            </div>

            <div className="bg-card border rounded-xl p-4 flex items-center space-x-4 shadow-sm">
                <div className="p-3 bg-slate-500/10 text-slate-600 rounded-full">
                    <HelpCircle className="w-6 h-6" />
                </div>
                <div>
                    <p className="text-sm text-muted-foreground">Unbekannt / Kritisch</p>
                    <p className="text-2xl font-bold">{lowConfidence}</p>
                </div>
            </div>
        </div>
    );
}
