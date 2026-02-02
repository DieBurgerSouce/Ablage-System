/**
 * Locale-aware Formatting Utilities
 *
 * Provides formatting functions that adapt to the current language:
 * - German: 31.01.2026, 1.234,56 EUR
 * - English: Jan 31, 2026, EUR 1,234.56
 *
 * Uses Intl APIs for proper locale handling.
 *
 * @module lib/i18n/format
 */

import type { SupportedLanguage } from './i18n';
import { LOCALE_CODES, getCurrentLanguage } from './i18n';

// ============================================================================
// Types
// ============================================================================

export interface FormatOptions {
  /** Fallback string for null/undefined values */
  fallback?: string;
}

export interface CurrencyFormatOptions extends FormatOptions {
  /** Currency code (default: EUR) */
  currency?: string;
  /** Show currency symbol/code */
  showCurrency?: boolean;
  /** Number of decimal places */
  decimals?: number;
}

export interface DateFormatOptions extends FormatOptions {
  /** Date format style */
  format?: 'short' | 'medium' | 'long' | 'full';
  /** Include time */
  includeTime?: boolean;
  /** Include seconds in time */
  includeSeconds?: boolean;
}

export interface NumberFormatOptions extends FormatOptions {
  /** Decimal places */
  decimals?: number;
  /** Minimum decimal places */
  minDecimals?: number;
  /** Maximum decimal places */
  maxDecimals?: number;
  /** Use grouping separators */
  useGrouping?: boolean;
}

export interface PercentFormatOptions extends FormatOptions {
  /** Decimal places */
  decimals?: number;
  /** Input is already a percentage (not decimal) */
  isPercentage?: boolean;
}

// ============================================================================
// Locale-aware formatting functions factory
// ============================================================================

/**
 * Create locale-aware formatting functions for a specific language
 */
export function formatByLocale(language: SupportedLanguage) {
  const locale = LOCALE_CODES[language];
  const isGerman = language === 'de';

  // -------------------------------------------------------------------------
  // Currency Formatting
  // -------------------------------------------------------------------------

  /**
   * Format a number as currency
   *
   * German: 1.234,56 EUR or 1.234,56 EUR
   * English: EUR 1,234.56 or EUR1,234.56
   */
  function currency(
    amount: number | string | null | undefined,
    options: CurrencyFormatOptions = {}
  ): string {
    const { currency: currencyCode = 'EUR', showCurrency = true, decimals = 2, fallback = '-' } = options;

    if (amount === null || amount === undefined || amount === '') {
      return fallback;
    }

    const numAmount = typeof amount === 'string' ? parseFloat(amount) : amount;

    if (isNaN(numAmount)) {
      return fallback;
    }

    if (!showCurrency) {
      return new Intl.NumberFormat(locale, {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      }).format(numAmount);
    }

    // For German, format number and append currency code
    // For English, use standard Intl currency formatting
    if (isGerman) {
      const formatted = new Intl.NumberFormat(locale, {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      }).format(numAmount);
      return `${formatted} ${currencyCode}`;
    } else {
      return new Intl.NumberFormat(locale, {
        style: 'currency',
        currency: currencyCode,
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      }).format(numAmount);
    }
  }

  /**
   * Format currency in compact form for dashboards
   */
  function currencyCompact(
    amount: number | null | undefined,
    options: CurrencyFormatOptions = {}
  ): string {
    const { currency: currencyCode = 'EUR', fallback = '-' } = options;

    if (amount === null || amount === undefined || isNaN(amount)) {
      return fallback;
    }

    const absAmount = Math.abs(amount);
    const sign = amount < 0 ? '-' : '';

    if (absAmount >= 1_000_000) {
      const millions = absAmount / 1_000_000;
      const suffix = isGerman ? 'Mio.' : 'M';
      return `${sign}${number(millions, { decimals: 2 })} ${suffix} ${currencyCode}`;
    }

    if (absAmount >= 100_000) {
      const thousands = absAmount / 1_000;
      const suffix = isGerman ? 'Tsd.' : 'K';
      return `${sign}${number(thousands, { decimals: 0 })} ${suffix} ${currencyCode}`;
    }

    return currency(amount, options);
  }

  // -------------------------------------------------------------------------
  // Date Formatting
  // -------------------------------------------------------------------------

  /**
   * Format a date
   *
   * German: 31.01.2026 (short), 31. Januar 2026 (long)
   * English: Jan 31, 2026 (short), January 31, 2026 (long)
   */
  function date(
    value: Date | string | null | undefined,
    options: DateFormatOptions = {}
  ): string {
    const { format = 'short', fallback = '-' } = options;

    if (!value) {
      return fallback;
    }

    const dateObj = typeof value === 'string' ? new Date(value) : value;

    if (isNaN(dateObj.getTime())) {
      return fallback;
    }

    const formatOptions: Intl.DateTimeFormatOptions = {
      short: { day: '2-digit', month: '2-digit', year: 'numeric' },
      medium: { day: '2-digit', month: 'short', year: 'numeric' },
      long: { day: 'numeric', month: 'long', year: 'numeric' },
      full: { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' },
    }[format];

    return new Intl.DateTimeFormat(locale, formatOptions).format(dateObj);
  }

  /**
   * Format date and time
   */
  function dateTime(
    value: Date | string | null | undefined,
    options: DateFormatOptions = {}
  ): string {
    const { includeSeconds = false, fallback = '-' } = options;

    if (!value) {
      return fallback;
    }

    const dateObj = typeof value === 'string' ? new Date(value) : value;

    if (isNaN(dateObj.getTime())) {
      return fallback;
    }

    const formatOptions: Intl.DateTimeFormatOptions = {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      ...(includeSeconds ? { second: '2-digit' } : {}),
    };

    return new Intl.DateTimeFormat(locale, formatOptions).format(dateObj);
  }

  /**
   * Format time only
   */
  function time(
    value: Date | string | null | undefined,
    options: DateFormatOptions = {}
  ): string {
    const { includeSeconds = false, fallback = '-' } = options;

    if (!value) {
      return fallback;
    }

    const dateObj = typeof value === 'string' ? new Date(value) : value;

    if (isNaN(dateObj.getTime())) {
      return fallback;
    }

    const formatOptions: Intl.DateTimeFormatOptions = {
      hour: '2-digit',
      minute: '2-digit',
      ...(includeSeconds ? { second: '2-digit' } : {}),
    };

    return new Intl.DateTimeFormat(locale, formatOptions).format(dateObj);
  }

  /**
   * Format relative date (e.g., "vor 5 Minuten", "5 minutes ago")
   */
  function relativeDate(
    value: Date | string | null | undefined,
    options: FormatOptions = {}
  ): string {
    const { fallback = '-' } = options;

    if (!value) {
      return fallback;
    }

    const dateObj = typeof value === 'string' ? new Date(value) : value;

    if (isNaN(dateObj.getTime())) {
      return fallback;
    }

    const now = new Date();
    const diffMs = now.getTime() - dateObj.getTime();
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHours = Math.floor(diffMin / 60);
    const diffDays = Math.floor(diffHours / 24);
    const diffWeeks = Math.floor(diffDays / 7);
    const diffMonths = Math.floor(diffDays / 30);

    // Use Intl.RelativeTimeFormat
    const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });

    if (diffSec < 60) {
      return rtf.format(-diffSec, 'second');
    }
    if (diffMin < 60) {
      return rtf.format(-diffMin, 'minute');
    }
    if (diffHours < 24) {
      return rtf.format(-diffHours, 'hour');
    }
    if (diffDays < 7) {
      return rtf.format(-diffDays, 'day');
    }
    if (diffWeeks < 4) {
      return rtf.format(-diffWeeks, 'week');
    }
    if (diffMonths < 12) {
      return rtf.format(-diffMonths, 'month');
    }

    return date(dateObj);
  }

  // -------------------------------------------------------------------------
  // Number Formatting
  // -------------------------------------------------------------------------

  /**
   * Format a number
   *
   * German: 1.234.567,89
   * English: 1,234,567.89
   */
  function number(
    value: number | string | null | undefined,
    options: NumberFormatOptions = {}
  ): string {
    const { decimals = 2, minDecimals, maxDecimals, useGrouping = true, fallback = '-' } = options;

    if (value === null || value === undefined || value === '') {
      return fallback;
    }

    const numValue = typeof value === 'string' ? parseFloat(value) : value;

    if (isNaN(numValue)) {
      return fallback;
    }

    return new Intl.NumberFormat(locale, {
      minimumFractionDigits: minDecimals ?? decimals,
      maximumFractionDigits: maxDecimals ?? decimals,
      useGrouping,
    }).format(numValue);
  }

  /**
   * Format as integer (no decimals)
   */
  function integer(
    value: number | string | null | undefined,
    options: FormatOptions = {}
  ): string {
    return number(value, { ...options, decimals: 0 });
  }

  /**
   * Format as percentage
   *
   * German: 12,34 %
   * English: 12.34%
   */
  function percent(
    value: number | null | undefined,
    options: PercentFormatOptions = {}
  ): string {
    const { decimals = 2, isPercentage = false, fallback = '-' } = options;

    if (value === null || value === undefined || isNaN(value)) {
      return fallback;
    }

    // If input is decimal (0.1234), multiply by 100
    const percentValue = isPercentage ? value : value * 100;

    const formatted = new Intl.NumberFormat(locale, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }).format(percentValue);

    return isGerman ? `${formatted} %` : `${formatted}%`;
  }

  // -------------------------------------------------------------------------
  // File Size Formatting
  // -------------------------------------------------------------------------

  /**
   * Format file size
   *
   * German: 1,5 MB
   * English: 1.5 MB
   */
  function fileSize(bytes: number | null | undefined, options: FormatOptions = {}): string {
    const { fallback = '-' } = options;

    if (bytes === null || bytes === undefined || isNaN(bytes) || bytes < 0) {
      return fallback;
    }

    const units = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    let unitIndex = 0;
    let size = bytes;

    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex++;
    }

    const decimals = unitIndex === 0 ? 0 : 1;
    return `${number(size, { decimals })} ${units[unitIndex]}`;
  }

  // -------------------------------------------------------------------------
  // German-specific Formatting
  // -------------------------------------------------------------------------

  /**
   * Format IBAN with spaces
   */
  function iban(value: string | null | undefined, options: FormatOptions = {}): string {
    const { fallback = '-' } = options;

    if (!value) {
      return fallback;
    }

    const cleaned = value.replace(/\s/g, '').toUpperCase();
    return cleaned.replace(/(.{4})/g, '$1 ').trim();
  }

  /**
   * Format German VAT ID
   */
  function vatId(value: string | null | undefined, options: FormatOptions = {}): string {
    const { fallback = '-' } = options;

    if (!value) {
      return fallback;
    }

    const cleaned = value.replace(/\s/g, '').toUpperCase();

    // German VAT ID: DE + 9 digits
    if (cleaned.startsWith('DE') && cleaned.length === 11) {
      return `DE ${cleaned.slice(2, 5)} ${cleaned.slice(5, 8)} ${cleaned.slice(8)}`;
    }

    // Other: Country code + rest
    const countryCode = cleaned.slice(0, 2);
    const rest = cleaned.slice(2);
    return `${countryCode} ${rest}`;
  }

  // -------------------------------------------------------------------------
  // List Formatting
  // -------------------------------------------------------------------------

  /**
   * Format a list of items
   *
   * German: "A, B und C"
   * English: "A, B, and C"
   */
  function list(items: string[], options: FormatOptions = {}): string {
    const { fallback = '-' } = options;

    if (!items || items.length === 0) {
      return fallback;
    }

    const formatter = new Intl.ListFormat(locale, { style: 'long', type: 'conjunction' });
    return formatter.format(items);
  }

  // -------------------------------------------------------------------------
  // Return all formatters
  // -------------------------------------------------------------------------

  return {
    currency,
    currencyCompact,
    date,
    dateTime,
    time,
    relativeDate,
    number,
    integer,
    percent,
    fileSize,
    iban,
    vatId,
    list,
    locale,
    isGerman,
  };
}

// ============================================================================
// Default formatters (using current language)
// ============================================================================

/**
 * Get format utilities for the current language
 */
export function getFormatters() {
  return formatByLocale(getCurrentLanguage());
}

// Export individual functions that use current language
export function formatCurrency(
  amount: number | string | null | undefined,
  options?: CurrencyFormatOptions
): string {
  return getFormatters().currency(amount, options);
}

export function formatDate(
  value: Date | string | null | undefined,
  options?: DateFormatOptions
): string {
  return getFormatters().date(value, options);
}

export function formatDateTime(
  value: Date | string | null | undefined,
  options?: DateFormatOptions
): string {
  return getFormatters().dateTime(value, options);
}

export function formatNumber(
  value: number | string | null | undefined,
  options?: NumberFormatOptions
): string {
  return getFormatters().number(value, options);
}

export function formatPercent(
  value: number | null | undefined,
  options?: PercentFormatOptions
): string {
  return getFormatters().percent(value, options);
}

export function formatFileSize(bytes: number | null | undefined, options?: FormatOptions): string {
  return getFormatters().fileSize(bytes, options);
}

export function formatRelativeDate(
  value: Date | string | null | undefined,
  options?: FormatOptions
): string {
  return getFormatters().relativeDate(value, options);
}

export default formatByLocale;
