import { useAnimatedCounter } from '@/hooks/use-animated-counter';

interface AnimatedNumberProps {
  /** The target number to display */
  value: number;
  /** Prefix text (e.g., "\u20ac") */
  prefix?: string;
  /** Suffix text (e.g., "%") */
  suffix?: string;
  /** Decimal places */
  decimals?: number;
  /** Additional CSS classes */
  className?: string;
  /** Animation duration in seconds */
  duration?: number;
}

export function AnimatedNumber({
  value,
  prefix = '',
  suffix = '',
  decimals = 0,
  className,
  duration,
}: AnimatedNumberProps) {
  const { displayValue } = useAnimatedCounter({
    targetValue: value,
    decimals,
    duration,
  });

  return (
    <span className={className} aria-live="polite">
      {prefix}{displayValue}{suffix}
    </span>
  );
}
