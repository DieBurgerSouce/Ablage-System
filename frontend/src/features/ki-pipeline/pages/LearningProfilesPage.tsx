/**
 * LearningProfilesPage
 * Learning profiles list - filterable by entity type
 */

import { useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { Brain, Users, FileText, Package } from 'lucide-react';
import { useLearningProfiles } from '../hooks/use-ki-pipeline-queries';
import { LearningProfileCard } from '../components/LearningProfileCard';

export function LearningProfilesPage() {
  const [entityType, setEntityType] = useState<
    'all' | 'supplier' | 'customer' | 'document_type'
  >('all');

  const { data: profiles, isLoading } = useLearningProfiles(
    entityType !== 'all' ? { entity_type: entityType } : undefined
  );

  const renderContent = () => {
    if (isLoading) {
      return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Skeleton key={i} className="h-64" />
          ))}
        </div>
      );
    }

    if (!profiles || profiles.length === 0) {
      return (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            Keine Lernprofile gefunden
          </CardContent>
        </Card>
      );
    }

    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {profiles.map((profile) => (
          <LearningProfileCard
            key={`${profile.entity_type}-${profile.entity_id}`}
            profile={profile}
          />
        ))}
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center gap-3">
          <Brain className="h-8 w-8 text-primary" />
          <div>
            <h1 className="text-3xl font-bold">Lernprofile</h1>
            <p className="text-muted-foreground">
              KI-Lernfortschritt nach Lieferant und Dokumenttyp
            </p>
          </div>
        </div>
      </div>

      {/* Tabs for Entity Type Filter */}
      <Tabs
        value={entityType}
        onValueChange={(v) =>
          setEntityType(v as typeof entityType)
        }
        className="w-full"
      >
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="all" className="gap-2">
            <Package className="h-4 w-4" />
            Alle
          </TabsTrigger>
          <TabsTrigger value="supplier" className="gap-2">
            <Users className="h-4 w-4" />
            Lieferanten
          </TabsTrigger>
          <TabsTrigger value="customer" className="gap-2">
            <Users className="h-4 w-4" />
            Kunden
          </TabsTrigger>
          <TabsTrigger value="document_type" className="gap-2">
            <FileText className="h-4 w-4" />
            Dokumenttypen
          </TabsTrigger>
        </TabsList>

        <TabsContent value="all" className="mt-6">
          {renderContent()}
        </TabsContent>
        <TabsContent value="supplier" className="mt-6">
          {renderContent()}
        </TabsContent>
        <TabsContent value="customer" className="mt-6">
          {renderContent()}
        </TabsContent>
        <TabsContent value="document_type" className="mt-6">
          {renderContent()}
        </TabsContent>
      </Tabs>
    </div>
  );
}
