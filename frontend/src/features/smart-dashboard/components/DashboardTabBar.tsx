// Dashboard Tab Navigation Component
// Tabs: Übersicht | Finanzen | Dokumente | Workflows | System

import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { DashboardTabKey, TAB_CONFIG } from '../types/smart-dashboard-types';

interface DashboardTabBarProps {
  activeTab: DashboardTabKey;
  onTabChange: (tab: DashboardTabKey) => void;
}

export function DashboardTabBar({ activeTab, onTabChange }: DashboardTabBarProps) {
  const tabs: DashboardTabKey[] = ['uebersicht', 'finanzen', 'dokumente', 'workflows', 'system'];

  return (
    <Tabs value={activeTab} onValueChange={(value) => onTabChange(value as DashboardTabKey)}>
      <TabsList className="grid w-full grid-cols-5 lg:w-auto lg:inline-grid">
        {tabs.map((tab) => {
          const config = TAB_CONFIG[tab];
          const Icon = config.icon;

          return (
            <TabsTrigger
              key={tab}
              value={tab}
              className="flex items-center gap-2 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
            >
              <Icon className="h-4 w-4" />
              <span className="hidden sm:inline">{config.label}</span>
            </TabsTrigger>
          );
        })}
      </TabsList>
    </Tabs>
  );
}
