import { Badge } from "@/components/ui/badge";
import { FileText, Image, AlertCircle, CheckCircle2, Clock, Loader2 } from "lucide-react";

interface OCRStatusBadgeProps {
    status: 'pending' | 'processing' | 'completed' | 'failed';
    confidence?: number;
}

export function OCRStatusBadge({ status, confidence }: OCRStatusBadgeProps) {
    switch (status) {
        case 'completed':
            return (
                <Badge variant="outline" className="gap-1 border-success/50 text-success bg-success/10">
                    <CheckCircle2 className="w-3 h-3" />
                    {confidence ? `${Math.round(confidence * 100)}%` : 'OCR'}
                </Badge>
            );
        case 'processing':
            return (
                <Badge variant="outline" className="gap-1 border-primary/50 text-primary bg-primary/10">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Processing
                </Badge>
            );
        case 'failed':
            return (
                <Badge variant="destructive" className="gap-1">
                    <AlertCircle className="w-3 h-3" />
                    Failed
                </Badge>
            );
        default:
            return (
                <Badge variant="secondary" className="gap-1">
                    <Clock className="w-3 h-3" />
                    Pending
                </Badge>
            );
    }
}

interface DocumentTypeIconProps {
    mimeType: string;
}

export function DocumentTypeIcon({ mimeType }: DocumentTypeIconProps) {
    if (mimeType?.startsWith('image/')) {
        return <Image className="w-12 h-12 text-muted-foreground/50" />;
    }
    return <FileText className="w-12 h-12 text-muted-foreground/50" />;
}
