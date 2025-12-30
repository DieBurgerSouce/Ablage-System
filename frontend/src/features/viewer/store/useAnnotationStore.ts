import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface Annotation {
    id: string
    page: number
    type: 'highlight' | 'comment'
    x: number // percent
    y: number // percent
    w?: number // percent (for highlight)
    h?: number // percent (for highlight)
    content?: string
    color: string
    author?: string
    createdAt: number
}

interface AnnotationState {
    annotations: Annotation[]
    mode: 'view' | 'highlight' | 'comment'
    selectedId: string | null
    authorName: string // Mock for current user
    addAnnotation: (annotation: Annotation) => void
    removeAnnotation: (id: string) => void
    updateAnnotation: (id: string, updates: Partial<Annotation>) => void
    setMode: (mode: 'view' | 'highlight' | 'comment') => void
    selectAnnotation: (id: string | null) => void
    setAuthorName: (name: string) => void
}

export const useAnnotationStore = create<AnnotationState>()(
    persist(
        (set) => ({
            annotations: [],
            mode: 'view',
            selectedId: null,
            authorName: 'Admin User', // Default mock user
            addAnnotation: (annotation) => set((state) => ({
                annotations: [...state.annotations, { ...annotation, author: state.authorName, createdAt: Date.now() }]
            })),
            removeAnnotation: (id) => set((state) => ({
                annotations: state.annotations.filter((a) => a.id !== id)
            })),
            updateAnnotation: (id, updates) => set((state) => ({
                annotations: state.annotations.map(a => a.id === id ? { ...a, ...updates } : a)
            })),
            setMode: (mode) => set({ mode }),
            selectAnnotation: (selectedId) => set({ selectedId }),
            setAuthorName: (authorName) => set({ authorName }),
        }),
        {
            name: 'annotation-storage', // unique name
            partialize: (state) => ({ annotations: state.annotations, authorName: state.authorName }), // only persist data, not UI state
        }
    )
)
