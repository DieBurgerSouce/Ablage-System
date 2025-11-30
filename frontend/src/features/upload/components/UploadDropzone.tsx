import { useDropzone } from 'react-dropzone';
import { motion } from 'framer-motion';
import { Upload } from 'lucide-react';

const dropzoneVariants = {
    idle: { borderColor: 'var(--border)', scale: 1 },
    active: {
        borderColor: 'var(--primary)',
        backgroundColor: 'oklch(0.35 0.08 250 / 0.05)',
        scale: 1.01
    },
    reject: { borderColor: 'var(--destructive)' }
};

interface UploadDropzoneProps {
    onFilesAdd: (files: File[]) => void;
}

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
        <motion.div
            {...getRootProps()}
            variants={dropzoneVariants}
            animate={isDragReject ? 'reject' : isDragActive ? 'active' : 'idle'}
            className="border-2 border-dashed rounded-xl p-12 cursor-pointer flex flex-col items-center justify-center text-center transition-colors bg-card"
        >
            <input {...getInputProps()} />
            <Upload className="w-16 h-16 text-primary mb-4" />
            <p className="text-lg font-medium">
                {isDragActive ? 'Dateien hier ablegen' : 'Dateien hierher ziehen oder klicken'}
            </p>
            <p className="text-sm text-muted-foreground mt-2">PDF, PNG, JPG • Max. 50MB</p>
        </motion.div>
    );
}
