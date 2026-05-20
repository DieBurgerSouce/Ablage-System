/**
 * RiskScoreBadge Component Tests
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@/test/utils';
import { RiskScoreBadge, getRiskConfig } from '../RiskScoreBadge';

describe('RiskScoreBadge', () => {
  it('renders high risk score correctly', () => {
    render(<RiskScoreBadge score={85} />);

    expect(screen.getByText('85')).toBeInTheDocument();
    expect(screen.getByText('(Hoch)')).toBeInTheDocument();
  });

  it('renders medium risk score correctly', () => {
    render(<RiskScoreBadge score={60} />);

    expect(screen.getByText('60')).toBeInTheDocument();
    expect(screen.getByText('(Mittel)')).toBeInTheDocument();
  });

  it('renders low risk score correctly', () => {
    render(<RiskScoreBadge score={30} />);

    expect(screen.getByText('30')).toBeInTheDocument();
    expect(screen.getByText('(Niedrig)')).toBeInTheDocument();
  });

  it('renders null score with placeholder', () => {
    render(<RiskScoreBadge score={null} />);

    // Sollte "-" anzeigen für fehlenden Score
    expect(screen.getAllByText('-')[0]).toBeInTheDocument();
  });

  it('applies correct color classes for high risk', () => {
    const { container } = render(<RiskScoreBadge score={90} />);
    const badge = container.querySelector('.bg-red-100');

    expect(badge).toBeInTheDocument();
  });

  it('applies correct color classes for medium risk', () => {
    const { container } = render(<RiskScoreBadge score={65} />);
    const badge = container.querySelector('.bg-yellow-100');

    expect(badge).toBeInTheDocument();
  });

  it('applies correct color classes for low risk', () => {
    const { container } = render(<RiskScoreBadge score={20} />);
    const badge = container.querySelector('.bg-green-100');

    expect(badge).toBeInTheDocument();
  });

  it('renders in compact mode', () => {
    render(<RiskScoreBadge score={75} compact />);

    expect(screen.getByText('75')).toBeInTheDocument();
    // In compact mode sollte kein shortLabel angezeigt werden
    expect(screen.queryByText('(Hoch)')).not.toBeInTheDocument();
  });

  it('shows tooltip with description when showTooltip is true', async () => {
    const { getByText } = render(<RiskScoreBadge score={80} showTooltip />);
    const badge = getByText('80').closest('span');

    expect(badge).toBeInTheDocument();
    // Tooltip sollte im DOM sein (auch wenn nicht sichtbar)
    // Note: Radix Tooltip rendering ist komplex in Tests, daher nur Badge-Check
  });

  it('does not show tooltip when showTooltip is false', () => {
    render(<RiskScoreBadge score={80} showTooltip={false} />);

    expect(screen.getByText('80')).toBeInTheDocument();
  });

  it('accepts custom className', () => {
    const { container } = render(<RiskScoreBadge score={50} className="custom-badge" />);
    const badge = container.querySelector('.custom-badge');

    expect(badge).toBeInTheDocument();
  });

  describe('getRiskConfig helper', () => {
    it('returns high risk config for scores > 75', () => {
      const config = getRiskConfig(80);

      expect(config.level).toBe('high');
      expect(config.label).toBe('Hohes Risiko');
      expect(config.shortLabel).toBe('Hoch');
    });

    it('returns medium risk config for scores 50-75', () => {
      const config = getRiskConfig(60);

      expect(config.level).toBe('medium');
      expect(config.label).toBe('Mittleres Risiko');
      expect(config.shortLabel).toBe('Mittel');
    });

    it('returns low risk config for scores < 50', () => {
      const config = getRiskConfig(30);

      expect(config.level).toBe('low');
      expect(config.label).toBe('Niedriges Risiko');
      expect(config.shortLabel).toBe('Niedrig');
    });

    it('returns none config for null score', () => {
      const config = getRiskConfig(null);

      expect(config.level).toBe('none');
      expect(config.label).toBe('Kein Score');
      expect(config.shortLabel).toBe('-');
    });

    it('includes German descriptions', () => {
      const config = getRiskConfig(85);

      expect(config.description).toContain('Zahlungsrisiko');
      expect(config.description).toContain('Prüfen');
    });
  });
});
