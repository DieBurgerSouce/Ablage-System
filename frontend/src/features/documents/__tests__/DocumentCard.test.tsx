import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { DocumentCard } from '../components/DocumentCard';

describe('DocumentCard', () => {
    const mockDocument = {
        id: '1',
        name: 'Test Document.pdf',
        mimeType: 'application/pdf',
        createdAt: new Date().toISOString(),
        ocrStatus: 'completed' as const,
        ocrConfidence: 0.98,
        size: 1024
    };

    it('renders document name', () => {
        render(<DocumentCard document={mockDocument} isSelected={false} onClick={vi.fn()} onDoubleClick={vi.fn()} onSelect={vi.fn()} />);
        expect(screen.getByText('Test Document.pdf')).toBeInTheDocument();
    });

    it('shows selected state', () => {
        const { container } = render(<DocumentCard document={mockDocument} isSelected={true} onClick={vi.fn()} onDoubleClick={vi.fn()} onSelect={vi.fn()} />);
        // Check for the ring class which indicates selection
        expect(container.firstChild).toHaveClass('ring-2');
    });

    it('calls onClick on click', () => {
        const onClick = vi.fn();
        render(<DocumentCard document={mockDocument} isSelected={false} onClick={onClick} onDoubleClick={vi.fn()} onSelect={vi.fn()} />);
        fireEvent.click(screen.getByText('Test Document.pdf'));
        expect(onClick).toHaveBeenCalled();
    });
});
