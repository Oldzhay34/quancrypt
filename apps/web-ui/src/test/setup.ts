import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';
import { clearStoredToken } from '@/shared/auth/token';

afterEach(() => {
    cleanup();
    clearStoredToken();
    window.sessionStorage.clear();
    window.localStorage.clear();
});
