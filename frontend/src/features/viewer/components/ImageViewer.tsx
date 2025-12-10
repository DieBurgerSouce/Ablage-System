import { useState, useRef, useEffect, useCallback } from 'react';
import { BoundingBoxOverlay, type BoundingBox } from './BoundingBoxOverlay';
import { apiClient } from '@/lib/api/client';

interface ImageViewerProps {
    fileUrl: string;
    scale: number;
    boxes?: BoundingBox[];
    selectedBox: BoundingBox | null;
    onBoxClick: (box: BoundingBox | null) => void;
    onLoadSuccess?: () => void;
    onLoadError?: (error: Error) => void;
}

export function ImageViewer({
    fileUrl,
    scale,
    boxes = [],
    selectedBox,
    onBoxClick,
    onLoadSuccess,
    onLoadError
}: ImageViewerProps) {
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [naturalSize, setNaturalSize] = useState<{ width: number; height: number } | null>(null);
    const [blobUrl, setBlobUrl] = useState<string | null>(null);
    const [containerSize, setContainerSize] = useState<{ width: number; height: number } | null>(null);
    const imgRef = useRef<HTMLImageElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);

    // Observe container size changes
    useEffect(() => {
        const container = containerRef.current;
        if (!container) return;

        const updateSize = () => {
            setContainerSize({
                width: container.clientWidth,
                height: container.clientHeight
            });
        };

        // Initial size
        updateSize();

        // Observe resize
        const resizeObserver = new ResizeObserver(updateSize);
        resizeObserver.observe(container);

        return () => resizeObserver.disconnect();
    }, []);

    // Fetch image with authentication
    useEffect(() => {
        let cancelled = false;
        setIsLoading(true);
        setError(null);
        setBlobUrl(null);
        setNaturalSize(null);

        const fetchImage = async () => {
            try {
                const response = await apiClient.get(fileUrl, {
                    responseType: 'blob'
                });

                if (cancelled) return;

                const url = URL.createObjectURL(response.data);
                setBlobUrl(url);
            } catch (err) {
                if (cancelled) return;
                console.error('Failed to load image:', err);
                setError('Bild konnte nicht geladen werden');
                setIsLoading(false);
                onLoadError?.(err instanceof Error ? err : new Error('Failed to load image'));
            }
        };

        fetchImage();

        return () => {
            cancelled = true;
        };
    }, [fileUrl]);

    // Cleanup blob URL on unmount or URL change
    useEffect(() => {
        return () => {
            if (blobUrl) {
                URL.revokeObjectURL(blobUrl);
            }
        };
    }, [blobUrl]);

    const handleLoad = useCallback(() => {
        setIsLoading(false);
        if (imgRef.current) {
            setNaturalSize({
                width: imgRef.current.naturalWidth,
                height: imgRef.current.naturalHeight
            });
        }
        onLoadSuccess?.();
    }, [onLoadSuccess]);

    const handleError = useCallback(() => {
        setIsLoading(false);
        const err = new Error('Bild konnte nicht geladen werden');
        setError(err.message);
        onLoadError?.(err);
    }, [onLoadError]);

    // Calculate dimensions to fit container
    const calculateDimensions = () => {
        if (!naturalSize || !containerSize) return undefined;

        const padding = 32;
        const availableWidth = containerSize.width - padding;
        const availableHeight = containerSize.height - padding;

        // Calculate scale to fit
        const scaleX = availableWidth / naturalSize.width;
        const scaleY = availableHeight / naturalSize.height;
        const baseScale = Math.min(scaleX, scaleY, 1); // Don't scale up beyond 100%

        // Apply user zoom on top of base scale
        const effectiveScale = baseScale * scale;

        return {
            width: naturalSize.width * effectiveScale,
            height: naturalSize.height * effectiveScale,
            effectiveScale
        };
    };

    const dimensions = calculateDimensions();

    return (
        <div
            ref={containerRef}
            className="w-full h-full overflow-auto bg-muted/30 flex items-start justify-center p-4"
        >
            {isLoading && (
                <div className="flex items-center justify-center p-8 h-full">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
                </div>
            )}

            {error && (
                <div className="p-8 text-center text-destructive">
                    <p>{error}</p>
                </div>
            )}

            {blobUrl && !error && (
                <div
                    className="relative inline-block shadow-lg bg-white flex-shrink-0"
                    style={{
                        width: dimensions?.width,
                        height: dimensions?.height,
                    }}
                >
                    <img
                        ref={imgRef}
                        src={blobUrl}
                        alt="Dokument"
                        onLoad={handleLoad}
                        onError={handleError}
                        style={{
                            width: '100%',
                            height: '100%',
                            display: isLoading ? 'none' : 'block',
                            objectFit: 'contain',
                        }}
                        className="select-none"
                        draggable={false}
                    />

                    {!isLoading && naturalSize && dimensions && (
                        <BoundingBoxOverlay
                            boxes={boxes}
                            scale={dimensions.effectiveScale}
                            selectedBox={selectedBox}
                            onBoxClick={onBoxClick}
                        />
                    )}
                </div>
            )}
        </div>
    );
}
