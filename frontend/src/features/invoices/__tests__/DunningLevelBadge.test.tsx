/**
 * DunningLevelBadge Unit Tests
 */

import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { DunningLevelBadge, DunningLevelBadgeCompact } from '../components/DunningLevelBadge';

describe('DunningLevelBadge', () => {
  it('rendert Level 0 mit korrektem Label', () => {
    render(<DunningLevelBadge level={0} />);
    expect(screen.getByText('-')).toBeInTheDocument();
  });

  it('rendert Level 1 als Erinnerung', () => {
    render(<DunningLevelBadge level={1} />);
    expect(screen.getByText('Erinnerung')).toBeInTheDocument();
  });

  it('rendert Level 2 als 1. Mahnung', () => {
    render(<DunningLevelBadge level={2} />);
    expect(screen.getByText('1. Mahnung')).toBeInTheDocument();
  });

  it('rendert Level 3 als 2. Mahnung', () => {
    render(<DunningLevelBadge level={3} />);
    expect(screen.getByText('2. Mahnung')).toBeInTheDocument();
  });

  it('rendert Level 4 als Letzte Mahnung', () => {
    render(<DunningLevelBadge level={4} />);
    expect(screen.getByText('Letzte Mahnung')).toBeInTheDocument();
  });

  it('zeigt Level-Nummer wenn showLabel=false', () => {
    render(<DunningLevelBadge level={2} showLabel={false} />);
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('akzeptiert benutzerdefinierte className', () => {
    const { container } = render(<DunningLevelBadge level={1} className="custom-class" />);
    expect(container.querySelector('.custom-class')).toBeInTheDocument();
  });
});

describe('DunningLevelBadgeCompact', () => {
  it('rendert Level 0 als einfaches "-"', () => {
    render(<DunningLevelBadgeCompact level={0} />);
    expect(screen.getByText('-')).toBeInTheDocument();
  });

  it('rendert Level 1+ als Badge mit Nummer', () => {
    render(<DunningLevelBadgeCompact level={3} />);
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('hat keine Badge für Level 0', () => {
    const { container } = render(<DunningLevelBadgeCompact level={0} />);
    // Should be a span, not a Badge
    const badge = container.querySelector('[class*="badge"]');
    expect(badge).toBeNull();
  });
});
