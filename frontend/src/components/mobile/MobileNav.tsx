/**
 * MobileNav Component
 *
 * Mobile-optimized bottom navigation bar for PWA.
 *
 * Features:
 * - Bottom navigation with icons
 * - Active state indication
 * - Safe area support (notch/home indicator)
 * - Badge counts for notifications
 * - Haptic feedback (where supported)
 * - Swipe gesture support
 *
 * All user-facing text is in German.
 */

import * as React from 'react';
import { useNavigate, useLocation } from '@tanstack/react-router';
import { Home, FolderOpen, Search, Bell, User, Plus, type LucideIcon } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { useSafeAreaInsets } from '@/lib/mobile';
import { usePWA } from '@/context/PWAContext';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api/client';

// ============================================
// Types
// ============================================

export interface MobileNavProps {
  /** Custom className */
  className?: string;
  /** Hide on scroll */
  hideOnScroll?: boolean;
  /** Show floating action button */
  showFAB?: boolean;
  /** FAB click handler */
  onFABClick?: () => void;
  /** Custom navigation items */
  items?: NavItem[];
}

export interface NavItem {
  id: string;
  label: string;
  icon: LucideIcon;
  /** Navigation path */
  path?: string;
  /** Click handler (overrides path) */
  onClick?: () => void;
  /** Badge count */
  count?: number;
  /** Active path pattern (regex) */
  activePattern?: RegExp;
  /** Requires online */
  requiresOnline?: boolean;
}

interface NavCounts {
  unreadNotifications: number;
  pendingApprovals: number;
}

// ============================================
// Default Navigation Items
// ============================================

const DEFAULT_NAV_ITEMS: NavItem[] = [
  {
    id: 'home',
    label: 'Start',
    icon: Home,
    path: '/',
    activePattern: /^\/$/,
  },
  {
    id: 'documents',
    label: 'Dokumente',
    icon: FolderOpen,
    path: '/documents',
    activePattern: /^\/documents/,
  },
  {
    id: 'search',
    label: 'Suchen',
    icon: Search,
    path: '/search',
    activePattern: /^\/search/,
  },
  {
    id: 'notifications',
    label: 'Meldungen',
    icon: Bell,
    path: '/notifications',
    activePattern: /^\/notifications/,
    requiresOnline: true,
  },
  {
    id: 'profile',
    label: 'Profil',
    icon: User,
    path: '/profile',
    activePattern: /^\/profile/,
  },
];

// ============================================
// API Hook
// ============================================

function useNavCounts() {
  const { isOnline } = usePWA();

  return useQuery<NavCounts>({
    queryKey: ['nav-counts'],
    queryFn: async () => {
      const response = await apiClient.get('/api/v1/notifications/counts');
      return response.data;
    },
    enabled: isOnline,
    staleTime: 60 * 1000, // 1 minute
    refetchInterval: 2 * 60 * 1000, // 2 minutes
    retry: 1,
  });
}

// ============================================
// Component
// ============================================

export function MobileNav({
  className,
  hideOnScroll = false,
  showFAB = true,
  onFABClick,
  items = DEFAULT_NAV_ITEMS,
}: MobileNavProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const insets = useSafeAreaInsets();
  const { isOnline } = usePWA();
  const { data: counts } = useNavCounts();

  const [isVisible, setIsVisible] = React.useState(true);
  const [lastScrollY, setLastScrollY] = React.useState(0);

  // Handle scroll hide behavior
  React.useEffect(() => {
    if (!hideOnScroll) return;

    const handleScroll = () => {
      const currentScrollY = window.scrollY;
      const isScrollingDown = currentScrollY > lastScrollY;
      const isNearTop = currentScrollY < 100;

      setIsVisible(!isScrollingDown || isNearTop);
      setLastScrollY(currentScrollY);
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, [hideOnScroll, lastScrollY]);

  /**
   * Get badge count for nav item
   */
  const getCount = React.useCallback(
    (itemId: string): number | undefined => {
      if (!counts) return undefined;

      switch (itemId) {
        case 'notifications':
          return counts.unreadNotifications;
        default:
          return undefined;
      }
    },
    [counts]
  );

  /**
   * Check if item is active
   */
  const isActive = React.useCallback(
    (item: NavItem): boolean => {
      if (item.activePattern) {
        return item.activePattern.test(location.pathname);
      }
      if (item.path) {
        return location.pathname === item.path;
      }
      return false;
    },
    [location.pathname]
  );

  /**
   * Handle navigation
   */
  const handleNavigation = React.useCallback(
    (item: NavItem) => {
      if (item.requiresOnline && !isOnline) {
        return;
      }

      // Trigger haptic feedback if available
      if ('vibrate' in navigator) {
        navigator.vibrate(10);
      }

      if (item.onClick) {
        item.onClick();
      } else if (item.path) {
        navigate({ to: item.path });
      }
    },
    [isOnline, navigate]
  );

  /**
   * Handle FAB click
   */
  const handleFABClick = React.useCallback(() => {
    // Trigger haptic feedback
    if ('vibrate' in navigator) {
      navigator.vibrate(20);
    }

    onFABClick?.();
  }, [onFABClick]);

  return (
    <>
      {/* Navigation Bar */}
      <nav
        className={cn(
          'fixed bottom-0 left-0 right-0 z-50',
          'bg-background/95 backdrop-blur-md border-t',
          'transition-transform duration-300 ease-out',
          !isVisible && 'translate-y-full',
          className
        )}
        style={{
          paddingBottom: Math.max(insets.bottom, 8),
        }}
        role="navigation"
        aria-label="Hauptnavigation"
      >
        <div className="flex items-center justify-around px-2">
          {items.map((item) => {
            const Icon = item.icon;
            const count = item.count ?? getCount(item.id);
            const active = isActive(item);
            const disabled = item.requiresOnline && !isOnline;

            return (
              <button
                key={item.id}
                onClick={() => handleNavigation(item)}
                disabled={disabled}
                className={cn(
                  'relative flex flex-col items-center justify-center',
                  'min-h-[56px] min-w-[56px] px-3 py-2',
                  'rounded-lg transition-colors',
                  'touch-manipulation',
                  active
                    ? 'text-primary'
                    : 'text-muted-foreground hover:text-foreground',
                  disabled && 'opacity-40 cursor-not-allowed'
                )}
                aria-current={active ? 'page' : undefined}
                aria-label={item.label}
              >
                {/* Icon with badge */}
                <div className="relative">
                  <Icon
                    className={cn(
                      'h-6 w-6 transition-transform',
                      active && 'scale-110'
                    )}
                  />
                  {count !== undefined && count > 0 && (
                    <Badge
                      variant="destructive"
                      className={cn(
                        'absolute -top-2 -right-2 h-5 min-w-5 px-1',
                        'text-[10px] flex items-center justify-center'
                      )}
                    >
                      {count > 99 ? '99+' : count}
                    </Badge>
                  )}
                </div>

                {/* Label */}
                <span
                  className={cn(
                    'text-[10px] font-medium mt-1',
                    active && 'font-semibold'
                  )}
                >
                  {item.label}
                </span>

                {/* Active indicator */}
                {active && (
                  <div className="absolute top-1 left-1/2 -translate-x-1/2 w-4 h-1 rounded-full bg-primary" />
                )}
              </button>
            );
          })}
        </div>
      </nav>

      {/* Floating Action Button */}
      {showFAB && (
        <button
          onClick={handleFABClick}
          className={cn(
            'fixed z-50 h-14 w-14 rounded-full',
            'bg-primary text-primary-foreground shadow-lg',
            'flex items-center justify-center',
            'transition-all duration-300 ease-out',
            'active:scale-95 hover:shadow-xl',
            !isVisible && 'translate-y-24'
          )}
          style={{
            bottom: 56 + Math.max(insets.bottom, 8) + 16,
            right: 16,
          }}
          aria-label="Neues Dokument"
        >
          <Plus className="h-6 w-6" />
        </button>
      )}

      {/* Spacer to prevent content from being hidden behind nav */}
      <div
        className="h-[56px]"
        style={{
          marginBottom: Math.max(insets.bottom, 8),
        }}
        aria-hidden="true"
      />
    </>
  );
}

/**
 * MobileNavSpacer - Spacer component for layouts using MobileNav
 * Use this at the bottom of scrollable content areas
 */
export function MobileNavSpacer() {
  const insets = useSafeAreaInsets();

  return (
    <div
      className="w-full"
      style={{
        height: 56 + Math.max(insets.bottom, 8),
      }}
      aria-hidden="true"
    />
  );
}

/**
 * useMobileNavHeight - Hook to get the mobile nav height
 */
export function useMobileNavHeight(): number {
  const insets = useSafeAreaInsets();
  return 56 + Math.max(insets.bottom, 8);
}

export default MobileNav;
