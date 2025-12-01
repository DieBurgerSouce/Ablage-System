import { useDropzone } from 'react-dropzone';
import { motion, type Variants } from 'framer-motion';
import { Upload, FileType, AlertCircle } from 'lucide-react';
import { motionTokens } from '@/lib/motion-tokens';
import { cn } from '@/lib/utils';

interface UploadDropzoneProps {
    onFilesAdd: (files: File[]) => void;
}

const dropzoneVariants: Variants = {
    idle: {
        borderColor: 'var(--border)',
        scale: 1,
        backgroundColor: 'transparent'
    },
    active: {
        borderColor: 'var(--primary)',
        backgroundColor: 'oklch(0.35 0.08 250 / 0.05)',
        scale: 1.01,
        transition: motionTokens.spring.snappy
    },
    reject: {
        borderColor: 'var(--destructive)',
        backgroundColor: 'oklch(0.55 0.22 25 / 0.05)',
        scale: 1,
        transition: motionTokens.spring.snappy
    }
};

const MotionDiv = motion.div as any;

export function UploadDropzone({ onFilesAdd }: UploadDropzoneProps) {
    const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
        onDrop: onFilesAdd,
        accept: {
            'application/pdf': ['.pdf'],
            'image/png': ['.png'],
            'image/jpeg': ['.jpg', '.jpeg']
        },
        maxSize: 50 * 1024 * 1024
    });

    return (
        <MotionDiv
            {...getRootProps()}
            variants={dropzoneVariants}
            animate={isDragReject ? 'reject' : isDragActive ? 'active' : 'idle'}
            className={cn(
                "border-2 border-dashed rounded-xl p-12 cursor-pointer flex flex-col items-center justify-center text-center transition-colors relative overflow-hidden group",
                "hover:border-primary/50 hover:bg-muted/30"
            )}
        >
            <input {...getInputProps()} />

            <div className="relative z-10 flex flex-col items-center gap-4">
                <div className={cn(
                    "w-20 h-20 rounded-2xl flex items-center justify-center transition-colors duration-300",
                    isDragReject ? "bg-destructive/10 text-destructive" :
                        isDragActive ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground group-hover:bg-primary/5 group-hover:text-primary"
                )}>
                    {isDragReject ? (
                        <AlertCircle className="w-10 h-10" />
                    ) : (
                        <Upload className="w-10 h-10" />
                    )}
                </div>

                <div className="space-y-1">
                    <h3 className="text-xl font-display font-medium">
                        {isDragReject ? 'Dateityp nicht unterstützt' :
                            isDragActive ? 'Dateien hier ablegen' : 'Dokumente hochladen'}
                    </h3>
                    <p className="text-sm text-muted-foreground max-w-xs mx-auto">
                        {isDragReject ? 'Bitte nur PDF, PNG oder JPG Dateien hochladen.' :
                            'Drag & Drop oder klicken zum Auswählen'}
                    </p>
                </div>

                <div className="flex items-center gap-3 text-xs text-muted-foreground mt-2 font-mono bg-muted/50 px-3 py-1.5 rounded-full border">
                    <span className="flex items-center gap-1.5">
                        <FileType className="w-3 h-3" /> PDF, PNG, JPG
                    </span>
                    <span className="w-px h-3 bg-border" />
                    <span>Max. 50MB</span>
                </div>
            </div>

            {/* Background Pattern */}
            <div className="absolute inset-0 opacity-[0.03] pointer-events-none noise-overlay" />
        </MotionDiv>
    );
}
