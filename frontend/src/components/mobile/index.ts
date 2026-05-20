/**
 * Mobile Components Index
 *
 * Phase 8: PWA Mobile Foundation
 *
 * Exportiert alle mobilen Komponenten:
 * - BottomSheet - Bottom Sheet Dialog
 * - SwipeableItem - Swipeable Listenelement
 * - MobileActionMenu - Kontextmenue
 * - PullToRefresh - Pull-to-Refresh
 * - CameraCapture - Document Scanner mit Multi-Page Support
 * - QuickActions - Schnellaktionen-Widget
 * - MobileNav - Bottom Navigation Bar
 */

// Bottom Sheet
export { BottomSheet } from "./BottomSheet"
export type { BottomSheetProps, SnapPoint } from "./BottomSheet"

// Swipeable Item
export { SwipeableItem } from "./SwipeableItem"
export type { SwipeableItemProps, SwipeAction, SwipeActionConfig } from "./SwipeableItem"

// Mobile Action Menu
export {
  MobileActionMenu,
  MobileActionTrigger,
} from "./MobileActionMenu"
export type {
  MobileActionMenuProps,
  MobileActionTriggerProps,
  MenuAction,
  MenuActionId,
} from "./MobileActionMenu"

// Pull to Refresh
export { PullToRefresh, usePullToRefresh } from "./PullToRefresh"
export type {
  PullToRefreshProps,
  UsePullToRefreshOptions,
  UsePullToRefreshReturn,
} from "./PullToRefresh"

// Camera Capture (Phase 8)
export { CameraCapture } from "./CameraCapture"
export type { CameraCaptureProps, CaptureResult } from "./CameraCapture"

// Quick Actions (Phase 8)
export { QuickActions, QuickActionsFAB } from "./QuickActions"
export type {
  QuickActionsProps,
  QuickActionsFABProps,
  QuickActionItem,
} from "./QuickActions"

// Mobile Navigation (Phase 8)
export { MobileNav, MobileNavSpacer, useMobileNavHeight } from "./MobileNav"
export type { MobileNavProps, NavItem } from "./MobileNav"
