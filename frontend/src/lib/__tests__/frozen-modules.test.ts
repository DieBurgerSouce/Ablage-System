/**
 * Unit-Tests: Frontend-Freeze-Gates (Odoo-Neuausrichtung 2026-07)
 *
 * Sichert die Freeze-Logik in lib/frozen-modules.ts ab:
 * - isPathFrozen matcht SEGMENTGENAU (kritisch: '/admin/datev' darf
 *   '/admin/datev-connect' nicht verschlucken — eigener Präfix-Eintrag —
 *   und Nicht-Freeze-Pfade wie '/kassenbuch' dürfen nicht am
 *   '/kasse'-Präfix hängenbleiben)
 * - aktive Kern-Routen (Archiv, Upload, Suche, Privat, …) sind NIE gefroren
 * - frozenModuleGuard wirft einen TanStack-Redirect auf /frozen?module=<key>
 * - die Registry bleibt konsistent (eindeutige Keys, deutsche Labels)
 */

import { describe, it, expect } from 'vitest'
import { isRedirect } from '@tanstack/react-router'
import {
  FROZEN_SECTIONS,
  frozenModuleGuard,
  getFrozenSection,
  isPathFrozen,
} from '../frozen-modules'

describe('isPathFrozen - Segmentgrenzen', () => {
  it('matcht den exakten Präfix und dessen Kindpfade', () => {
    expect(isPathFrozen('/admin/datev')).toEqual({ frozen: true, key: 'datev' })
    expect(isPathFrozen('/admin/datev/export')).toEqual({ frozen: true, key: 'datev' })
    expect(isPathFrozen('/banking')).toEqual({ frozen: true, key: 'banking' })
    expect(isPathFrozen('/admin/banking/reconciliation')).toEqual({
      frozen: true,
      key: 'banking',
    })
  })

  it("'/admin/datev-connect' matcht über den EIGENEN Präfix-Eintrag, nicht als Kind von '/admin/datev'", () => {
    // Beide Präfixe gehören zum Key 'datev', sind aber separate Einträge —
    // der Match darf NICHT über startsWith('/admin/datev') zustande kommen.
    expect(isPathFrozen('/admin/datev-connect')).toEqual({ frozen: true, key: 'datev' })
    expect(isPathFrozen('/admin/datev-connect/settings')).toEqual({
      frozen: true,
      key: 'datev',
    })
  })

  it('haengt NICHT an Segmentgrenzen: Präfix + weitere Zeichen ohne "/" ist kein Match', () => {
    // Wäre das Matching substring-basiert (startsWith ohne '/'-Grenze),
    // würden diese Pfade fälschlich einfrieren.
    expect(isPathFrozen('/admin/datev-neu').frozen).toBe(false)
    expect(isPathFrozen('/kassenbuch').frozen).toBe(false)
    expect(isPathFrozen('/bankingtools').frozen).toBe(false)
    expect(isPathFrozen('/holdingregister').frozen).toBe(false)
    expect(isPathFrozen('/riskante-route').frozen).toBe(false)
  })

  it('friert nur die Analytics-Subroute von /finanzen ein, nicht die Ablage-Ansicht', () => {
    expect(isPathFrozen('/finanzen').frozen).toBe(false)
    expect(isPathFrozen('/finanzen/2024').frozen).toBe(false)
    expect(isPathFrozen('/finanzen/zahlungsverhalten')).toEqual({
      frozen: true,
      key: 'finance',
    })
    expect(isPathFrozen('/finanzen/zahlungsverhalten/details')).toEqual({
      frozen: true,
      key: 'finance',
    })
  })

  it('laesst aktive Kern-Routen unangetastet (inkl. /frozen selbst)', () => {
    const activePaths = [
      '/',
      '/dashboard',
      '/documents',
      '/documents/abc/relationships',
      '/upload',
      '/scan',
      '/search',
      '/inbox',
      '/kunden',
      '/lieferanten',
      '/privat',
      '/vertraege',
      '/email-import',
      '/admin',
      '/admin/imports',
      '/admin/erp',
      '/monitoring',
      '/compliance',
      '/review-queue',
      '/frozen',
    ]
    for (const path of activePaths) {
      expect(isPathFrozen(path).frozen, `${path} muss aktiv bleiben`).toBe(false)
    }
  })
})

describe('getFrozenSection', () => {
  it('liefert die Sektion mit deutschem Label zum Key', () => {
    expect(getFrozenSection('lexware')?.label).toBe('Lexware-Import')
    expect(getFrozenSection('banking')?.label).toBe('Banking, Zahlungsverkehr & Mahnwesen')
  })

  it('liefert undefined fuer unbekannte oder fehlende Keys', () => {
    expect(getFrozenSection(undefined)).toBeUndefined()
    expect(getFrozenSection('gibt-es-nicht')).toBeUndefined()
  })
})

describe('frozenModuleGuard', () => {
  it('wirft einen TanStack-Redirect auf /frozen?module=<key>', () => {
    let thrown: unknown
    try {
      frozenModuleGuard('datev')
    } catch (e) {
      thrown = e
    }
    expect(thrown).toBeDefined()
    expect(isRedirect(thrown)).toBe(true)
    const options = (thrown as { options: { to?: string; search?: { module?: string }; replace?: boolean } })
      .options
    expect(options.to).toBe('/frozen')
    expect(options.search).toMatchObject({ module: 'datev' })
    expect(options.replace).toBe(true)
  })
})

describe('FROZEN_SECTIONS - Registry-Konsistenz', () => {
  it('hat 13 Sektionen mit eindeutigen Keys (Spiegel der Backend-Registry)', () => {
    const keys = FROZEN_SECTIONS.map((s) => s.key)
    expect(keys).toHaveLength(13)
    expect(new Set(keys).size).toBe(13)
  })

  it('jede Sektion hat ein deutsches Label und mindestens einen Routen-Präfix', () => {
    for (const section of FROZEN_SECTIONS) {
      expect(section.label.length, `Label fuer ${section.key}`).toBeGreaterThan(0)
      expect(section.routePrefixes.length, `Präfixe fuer ${section.key}`).toBeGreaterThan(0)
      for (const prefix of section.routePrefixes) {
        expect(prefix.startsWith('/'), `Präfix ${prefix} muss mit '/' beginnen`).toBe(true)
        expect(prefix.endsWith('/'), `Präfix ${prefix} ohne Trailing-Slash`).toBe(false)
      }
    }
  })
})
