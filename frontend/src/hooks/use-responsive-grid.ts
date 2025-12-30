import { useState, useEffect } from 'react';

type Breakpoint = 'sm' | 'md' | 'lg' | 'xl' | '2xl';

interface ResponsiveGridOptions {
    containerRef?: React.RefObject<HTMLElement | null>;
    defaultColumns?: number;
    breakpoints?: Partial<Record<Breakpoint, number>>;
}

/**
 * useResponsiveGrid
 *
 * Calculates the optimal number of columns based on container width.
 * Uses ResizeObserver for robust detection of container size changes.
 *
 * @example
 * const { columnCount } = useResponsiveGrid({ containerRef });
 */
export function useResponsiveGrid({
    containerRef,
    defaultColumns = 4,
    breakpoints = {
        sm: 1,    // < 640px
        md: 2,    // >= 640px
        lg: 3,    // >= 768px
        xl: 4,    // >= 1024px
        '2xl': 5  // >= 1280px
    }
}: ResponsiveGridOptions = {}) {
    const [columnCount, setColumnCount] = useState(defaultColumns);

    useEffect(() => {
        const updateColumns = (width: number) => {
            if (width < 640) {
                setColumnCount(breakpoints.sm ?? 1);
            } else if (width < 768) {
                setColumnCount(breakpoints.md ?? 2);
            } else if (width < 1024) {
                setColumnCount(breakpoints.lg ?? 3);
            } else if (width < 1280) {
                setColumnCount(breakpoints.xl ?? 4);
            } else {
                setColumnCount(breakpoints['2xl'] ?? 5);
            }
        };

        // If a container ref is provided, observe it
        if (containerRef?.current) {
            const observer = new ResizeObserver((entries) => {
                for (const entry of entries) {
                    updateColumns(entry.contentRect.width);
                }
            });

            observer.observe(containerRef.current);
            // Initial check
            updateColumns(containerRef.current.clientWidth);

            return () => observer.disconnect();
        }

        // Fallback to window resize if no container or during initialization (if needed)
        // For accurate component-based queries, ResizeObserver on container is preferred.
        // But if containerRef isn't ready yet, we might want a window listener or just wait.
        const handleWindowResize = () => {
            // Basic fallback purely on window width if preferred,
            // but usually strictly following container is better for embedded grids.
            updateColumns(window.innerWidth);
        };

        if (!containerRef) {
            window.addEventListener('resize', handleWindowResize);
            handleWindowResize();
            return () => window.removeEventListener('resize', handleWindowResize);
        }

    }, [containerRef, breakpoints]);

    return { columnCount };
}
