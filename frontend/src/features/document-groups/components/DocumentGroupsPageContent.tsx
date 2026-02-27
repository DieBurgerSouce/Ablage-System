import { DocumentGroupList } from '@/features/document-groups/components/DocumentGroupList'
import { DocumentGroupBrowser } from '@/features/document-groups/components/DocumentGroupBrowser'
import { GroupDetectionPanel } from '@/features/document-groups/components/GroupDetectionPanel'
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

export function DocumentGroupsPageContent() {
    return (
        <div className="p-8 space-y-8">
            <div className="flex justify-between items-start">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Dokumentgruppen</h1>
                    <p className="text-muted-foreground mt-2">
                        Verwalten Sie zusammengehörige Dokumente und Vorgänge.
                    </p>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
                <div className="lg:col-span-3 space-y-8">
                    <Tabs defaultValue="list">
                        <TabsList>
                            <TabsTrigger value="list">Übersicht</TabsTrigger>
                            <TabsTrigger value="browser">Gruppieren & Sortieren</TabsTrigger>
                        </TabsList>
                        <TabsContent value="list" className="mt-6">
                            <DocumentGroupList />
                        </TabsContent>
                        <TabsContent value="browser" className="mt-6">
                            <DocumentGroupBrowser />
                        </TabsContent>
                    </Tabs>
                </div>

                <div className="space-y-6">
                    <GroupDetectionPanel />
                </div>
            </div>
        </div>
    )
}
