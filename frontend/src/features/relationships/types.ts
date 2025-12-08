export type RelationshipType = 'related' | 'parent' | 'child' | 'duplicate' | 'reference';

export interface DocumentRelationship {
    id: string;
    sourceDocumentId: string;
    targetDocumentId: string;
    type: RelationshipType;
    createdAt: string;
    metadata?: Record<string, any>;
}

export interface RelationshipGraphNode {
    id: string;
    label: string;
    type: string; // 'document'
    data: {
        documentId: string;
        title: string;
        mimeType: string;
        thumbnail?: string;
    };
}

export interface RelationshipGraphEdge {
    id: string;
    source: string;
    target: string;
    label?: string;
    type?: string;
}
