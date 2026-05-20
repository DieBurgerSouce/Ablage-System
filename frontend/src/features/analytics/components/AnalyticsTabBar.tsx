// Analytics Tab Bar Component
// Tab navigation with 3 tabs: Betrieb, Finanzen, Team

import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { type AnalyticsTabKey, TAB_CONFIG } from '../types/analytics-types';

interface AnalyticsTabBarProps {
  activeTab: AnalyticsTabKey;
  onTabChange: (tab: AnalyticsTabKey) => void;
}

export function AnalyticsTabBar({ activeTab, onTabChange }: AnalyticsTabBarProps) {
  return (
    <Tabs
      value={activeTab}
      onValueChange={(value) => onTabChange(value as AnalyticsTabKey)}
    >
      <TabsList>
        {(Object.entries(TAB_CONFIG) as Array<[AnalyticsTabKey, { label: string }]>).map(
          ([key, config]) => (
            <TabsTrigger key={key} value={key}>
              {config.label}
            </TabsTrigger>
          ),
        )}
      </TabsList>
    </Tabs>
  );
}
