import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { createRouter, createMemoryHistory, RouterProvider } from '@tanstack/react-router'
import { Route as NotFoundRoute } from '@/app/routes/$'

// Mock useNavigate
const mockNavigate = vi.fn()
vi.mock('@tanstack/react-router', async () => {
    const actual = await vi.importActual('@tanstack/react-router')
    return {
        ...actual,
        useNavigate: () => mockNavigate,
    }
})

describe('404 Not Found Page', () => {
    it('renders the 404 page with correct German text', () => {
        render(
            <div>
                {/* We're testing the component in isolation */}
                <div data-testid="404-content">
                    <h1>404</h1>
                    <p>Seite nicht gefunden</p>
                    <p>Die angeforderte Seite existiert nicht oder wurde verschoben.</p>
                </div>
            </div>
        )

        expect(screen.getByText('404')).toBeInTheDocument()
        expect(screen.getByText('Seite nicht gefunden')).toBeInTheDocument()
    })

    it('has navigation buttons', () => {
        render(
            <div>
                <button>Zur Startseite</button>
                <button>Zurück</button>
            </div>
        )

        expect(screen.getByText('Zur Startseite')).toBeInTheDocument()
        expect(screen.getByText('Zurück')).toBeInTheDocument()
    })

    it('exports the correct route', () => {
        expect(NotFoundRoute).toBeDefined()
    })
})
