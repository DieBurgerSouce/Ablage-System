import { useNavigate } from '@tanstack/react-router'
import { UploadDropzone } from '@/features/upload/components/UploadDropzone'

export function UploadWidget() {
    const navigate = useNavigate()

    return (
        <section className="space-y-4">
            <h2 className="text-xl font-semibold">Dokument hochladen</h2>
            <UploadDropzone
                onFilesAdd={(files) => {
                    // Navigate zur Upload-Seite mit den ausgewählten Dateien
                    if (files.length > 0) {
                        navigate({ to: '/upload' })
                    }
                }}
            />
        </section>
    )
}
