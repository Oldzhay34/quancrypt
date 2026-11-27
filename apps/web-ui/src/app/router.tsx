import { createBrowserRouter, createMemoryRouter, Navigate } from 'react-router';
import type { RouteObject } from 'react-router';
import { SubscriptionPage, UsagePage } from '@/features/billing';
import { AnalysisPage, ChatPage } from '@/features/chat';
import { ConsentPage } from '@/features/consent';
import { InventoryPage } from '@/features/inventory';
import { PlanPage } from '@/features/plan';
import { SettingsPage } from '@/features/settings';
import { TopologyPage } from '@/features/topology';
import { ConsentGate, ProjectGate } from './gates';
import { AppShell } from './layout/AppShell';

export const appRoutes: RouteObject[] = [
    {
        element: <AppShell />,
        children: [
            {
                element: <ProjectGate />,
                children: [
                    { index: true, element: <Navigate to="/chat" replace /> },
                    { path: 'consent', element: <ConsentPage /> },
                    { path: 'settings', element: <SettingsPage /> },
                    { path: 'settings/usage', element: <UsagePage /> },
                    { path: 'subscription', element: <SubscriptionPage /> },
                    {
                        element: <ConsentGate />,
                        children: [
                            { path: 'chat', element: <ChatPage /> },
                            { path: 'analysis', element: <AnalysisPage /> },
                            { path: 'inventory', element: <InventoryPage /> },
                            { path: 'topology', element: <TopologyPage /> },
                            { path: 'plan', element: <PlanPage /> },
                        ],
                    },
                    { path: '*', element: <Navigate to="/chat" replace /> },
                ],
            },
        ],
    },
];

export const createAppRouter = () => createBrowserRouter(appRoutes);
export const createTestRouter = (path: string) => createMemoryRouter(appRoutes, { initialEntries: [path] });
