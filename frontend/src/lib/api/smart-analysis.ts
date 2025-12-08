import type { SmartAnalysisResult, Tune } from '@/features/upload/types';

export const AVAILABLE_TUNES: Tune[] = [
    {
        id: 'invoice-tune',
        name: 'Rechnungen & Finanzen',
        description: 'Optimiert für Rechnungen, Belege und Steuerdokumente.',
        icon: 'Receipt',
        color: 'bg-emerald-500'
    },
    {
        id: 'contract-tune',
        name: 'Verträge & Rechtliches',
        description: 'Erkennt Klauseln, Unterschriften und rechtliche Strukturen.',
        icon: 'Scale',
        color: 'bg-blue-500'
    },
    {
        id: 'correspondence-tune',
        name: 'Allgemeiner Schriftverkehr',
        description: 'Für Briefe, Notizen und sonstige Korrespondenz.',
        icon: 'Mail',
        color: 'bg-amber-500'
    },
    {
        id: 'technical-tune',
        name: 'Technische Dokumentation',
        description: 'Für Handbücher, Datenblätter und technische Zeichnungen.',
        icon: 'Wrench',
        color: 'bg-slate-500'
    }
];

export async function analyzeDocuments(files: File[], selectedTuneId: string): Promise<SmartAnalysisResult[]> {
    // Simulate network delay
    await new Promise(resolve => setTimeout(resolve, 2500));

    return files.map((file, index) => {
        // Mock logic for "Smart" detection
        let confidence: 'high' | 'medium' | 'low' = 'high';
        const issues: string[] = [];
        let detectedTuneId = selectedTuneId;

        // Simulate some "intelligence"
        if (file.name.toLowerCase().includes('scan')) {
            confidence = 'medium';
            issues.push('Niedrige Bildqualität möglich');
        }

        if (file.name.toLowerCase().includes('unknown')) {
            confidence = 'low';
            detectedTuneId = 'correspondence-tune'; // Suggest a different tune
        }

        // Simulate relationship detection (simple name matching for demo)
        // If this file has a similar name to the previous one, mark as attachment
        let isChild = false;
        let parentId = undefined;

        if (index > 0) {
            const prevFile = files[index - 1];
            if (file.name.startsWith(prevFile.name.split('.')[0])) {
                isChild = true;
                parentId = `file-${index - 1}`;
            }
        }

        return {
            fileId: `file-${index}`,
            fileName: file.name,
            fileSize: file.size,
            detectedTuneId,
            confidence,
            issues,
            isChild,
            parentId,
            previewUrl: URL.createObjectURL(file)
        };
    });
}
