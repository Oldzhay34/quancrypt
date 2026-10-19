import { createBrowserRouter, createMemoryRouter, Navigate } from 'react-router';
import type { RouteObject } from 'react-router';
import { ChatPage } from '@/features/chat';
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
                    {
                        element: <ConsentGate />,
                        children: [
                            { path: 'chat', element: <ChatPage /> },
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
