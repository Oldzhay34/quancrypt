import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router';
import { acquireToken } from '@/shared/auth';
import { AppProviders } from './providers';
import { createAppRouter } from './router';
import './global.css';

const root = document.getElementById('root');
if (!root) throw new Error('#root is missing');

// The token is taken from the fragment (and the fragment removed) before the router sees the address.
acquireToken();
const router = createAppRouter();
createRoot(root).render(
    <StrictMode>
        <AppProviders>
            <RouterProvider router={router} />
        </AppProviders>
    </StrictMode>,
);
