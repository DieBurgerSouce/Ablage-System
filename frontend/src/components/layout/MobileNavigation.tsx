/**
 * Mobile Navigation Component
 *
 * Bottom navigation bar optimized for mobile devices:
 * - Fixed bottom position
 * - Touch-friendly targets (48px minimum)
 * - Visual feedback on active state
 * - Badge support for notifications
 * - Safe area support for notched devices
 *
 * Phase 3.3 Feature 9: Mobile-First Dashboard
 */

import { useCallback, useMemo } from 'react';
import { Link, useLocation } from '@tanstack/react-router';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { FileText, Upload, Search, User, LayoutDashboard, type LucideIcon } from 'lucide-react';

// =============================================================================
// Types
// =============================================================================

export interface NavItem {
    id: string;
    label: string;
    icon: LucideIcon;
    href: string;
    badge?: number | string;
    /** Matches any path starting with href */
    matchPrefix?: boolean;
}

export interface MobileNavigationProps {
    /** Override default navigation items */
    items?: NavItem[];
    /** Additional CSS classes */
    className?: string;
    /** Show the navigation bar */
    visible?: boolean;
    /** Callback when item is clicked */
    onItemClick?: (item: NavItem) => void;
}

// =============================================================================
// Default Navigation Items
// =============================================================================

const DEFAULT_NAV_ITEMS: NavItem[] = [
    {
        id: 'dashboard',
        label: 'Dashboard',
        icon: LayoutDashboard,
        href: '/dashboard',
        matchPrefix: true,
    },
    {
        id: 'documents',
        label: 'Dokumente',
        icon: FileText,
        href: '/ablage',
        matchPrefix: true,
    },
    {
        id: 'upload',
        label: 'Upload',
        icon: Upload,
        href: '/upload',
    },
    {
        id: 'search',
        label: 'Suche',
        icon: Search,
        href: '/search',
    },
    {
        id: 'profile',
        label: 'Profil',
        icon: User,
        href: '/settings',
        matchPrefix: true,
    },
];

// =============================================================================
// Component
// =============================================================================

export function MobileNavigation({
    items = DEFAULT_NAV_ITEMS,
    className,
    visible = true,
    onItemClick,
}: MobileNavigationProps) {
    const location = useLocation();

    // Check if a nav item is active
    const isActive = useCallback(
        (item: NavItem): boolean => {
            if (item.matchPrefix) {
                return location.pathname.startsWith(item.href);
            }
            return location.pathname === item.href;
        },
        [location.pathname]
    );

    // Active item index for indicator animation
    const activeIndex = useMemo(() => {
        return items.findIndex((item) => isActive(item));
    }, [items, isActive]);

    if (!visible) return null;

    return (
        <nav
            className={cn(
                // Base styles
                'fixed bottom-0 left-0 right-0 z-50',
                'bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80',
                'border-t border-border',
                // Safe area padding for notched devices
                'pb-[env(safe-area-inset-bottom)]',
                // Hide on larger screens
                'md:hidden',
                className
            )}
            role="navigation"
            aria-label="Hauptnavigation"
        >
            {/* Active indicator */}
            {activeIndex >= 0 && (
                <div
                    className="absolute top-0 h-0.5 bg-primary transition-transform duration-200 ease-out"
                    style={{
                        width: `${100 / items.length}%`,
                        transform: `translateX(${activeIndex * 100}%)`,
                    }}
                />
            )}

            {/* Navigation items */}
            <ul className="flex items-center justify-around">
                {items.map((item) => {
                    const active = isActive(item);
                    const Icon = item.icon;

                    return (
                        <li key={item.id} className="flex-1">
                            <Link
                                to={item.href}
                                onClick={() => onItemClick?.(item)}
                                className={cn(
                                    // Base styles
                                    'flex flex-col items-center justify-center',
                                    'min-h-[64px] py-2 px-1',
                                    'text-xs font-medium',
                                    'transition-colors duration-150',
                                    'touch-manipulation',
                                    // Active state
                                    active
                                        ? 'text-primary'
                                        : 'text-muted-foreground hover:text-foreground',
                                    // Focus styles
                                    'focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2'
                                )}
                                aria-current={active ? 'page' : undefined}
                            >
                                {/* Icon with badge */}
                                <span className="relative mb-1">
                                    <Icon
                                        className={cn(
                                            'h-6 w-6 transition-transform duration-150',
                                            active && 'scale-110'
                                        )}
                                        strokeWidth={active ? 2.5 : 2}
                                    />
                                    {item.badge !== undefined && (
                                        <Badge
                                            variant="destructive"
                                            className={cn(
                                                'absolute -top-1 -right-2',
                                                'min-w-[18px] h-[18px] px-1',
                                                'text-[10px] font-bold',
                                                'flex items-center justify-center'
                                            )}
                                        >
                                            {typeof item.badge === 'number' && item.badge > 99
                                                ? '99+'
                                                : item.badge}
                                        </Badge>
                                    )}
                                </span>

                                {/* Label */}
                                <span
                                    className={cn(
                                        'truncate max-w-full',
                                        active && 'font-semibold'
                                    )}
                                >
                                    {item.label}
                                </span>
                            </Link>
                        </li>
                    );
                })}
            </ul>
        </nav>
    );
}

// =============================================================================
// Mobile Navigation with Notifications
// =============================================================================

interface MobileNavigationWithNotificationsProps extends MobileNavigationProps {
    /** Number of unread notifications */
    notificationCount?: number;
}

export function MobileNavigationWithNotifications({
    notificationCount = 0,
    items,
    ...props
}: MobileNavigationWithNotificationsProps) {
    const itemsWithBadge = useMemo(() => {
        const baseItems = items || DEFAULT_NAV_ITEMS;

        // Find profile item and add notification badge
        return baseItems.map((item) => {
            if (item.id === 'profile' && notificationCount > 0) {
                return { ...item, badge: notificationCount };
            }
            return item;
        });
    }, [items, notificationCount]);

    return <MobileNavigation items={itemsWithBadge} {...props} />;
}

// =============================================================================
// Spacer Component
// =============================================================================

/**
 * Spacer component to add padding at the bottom of content
 * to prevent it from being hidden behind the mobile navigation
 */
export function MobileNavigationSpacer({ className }: { className?: string }) {
    return (
        <div
            className={cn(
                // Height of nav + safe area
                'h-[64px] pb-[env(safe-area-inset-bottom)]',
                'md:hidden',
                className
            )}
            aria-hidden="true"
        />
    );
}

export default MobileNavigation;
