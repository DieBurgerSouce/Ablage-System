import type { SmartAnalysisResult } from '@/features/upload/types';

/**
 * Generates a UUID v4 string.
 * Used for unique file identification instead of index-based IDs.
 */
function generateUUID(): string {
    return crypto.randomUUID();
}

/**
 * Cleanup function to revoke blob URLs when analysis results are no longer needed.
 * IMPORTANT: Call this function when unmounting components or replacing analysis results
 * to prevent memory leaks from accumulated blob URLs.
 */
export function cleanupAnalysisResults(results: SmartAnalysisResult[]): void {
    for (const result of results) {
        if (result.previewUrl && result.previewUrl.startsWith('blob:')) {
            URL.revokeObjectURL(result.previewUrl);
        }
    }
}

export async function analyzeDocuments(files: File[], selectedTuneId: string, defaultBackendId: string): Promise<SmartAnalysisResult[]> {
    // Simulate network delay
    await new Promise(resolve => setTimeout(resolve, 2500));

    // Generate UUIDs for all files first to enable parent references
    const fileIds = files.map(() => generateUUID());

    return files.map((file, index) => {
        // Mock logic for "Smart" detection
        let confidence: 'high' | 'medium' | 'low' = 'high';
        const issues: string[] = [];
        const detectedTuneId = selectedTuneId;
        const selectedBackendId = defaultBackendId;

        // Simulate some "intelligence"
        if (file.name.toLowerCase().includes('scan')) {
            confidence = 'medium';
            issues.push('Niedrige Bildqualität möglich');
        }

        if (file.name.toLowerCase().includes('unknown')) {
            confidence = 'low';
        }

        // Simulate relationship detection
        // If this file has a similar name to the previous one, mark as attachment
        // Also check for "Anhang" or "Attachment" keywords
        let isChild = false;
        let parentId: string | undefined = undefined;

        if (index > 0) {
            const prevFile = files[index - 1];
            const isNameSimilar = file.name.startsWith(prevFile.name.split('.')[0]);
            const isAttachmentKeyword = /anhang|attachment|beilage/i.test(file.name);

            if (isNameSimilar || isAttachmentKeyword) {
                isChild = true;
                parentId = fileIds[index - 1]; // Reference by UUID
            }
        }

        return {
            fileId: fileIds[index], // UUID instead of index-based ID
            fileName: file.name,
            fileSize: file.size,
            detectedTuneId,
            selectedBackendId,
            confidence,
            issues,
            isChild,
            parentId,
            previewUrl: URL.createObjectURL(file)
        };
    });
}

