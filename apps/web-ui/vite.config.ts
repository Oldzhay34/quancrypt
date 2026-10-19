import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
    plugins: [react()],
    resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
    build: { target: 'es2022', sourcemap: false },
    server: { host: '127.0.0.1', port: 8080, strictPort: true },
    test: {
        environment: 'jsdom',
        setupFiles: ['./src/test/setup.ts'],
        css: { modules: { classNameStrategy: 'non-scoped' } },
        restoreMocks: true,
    },
});
