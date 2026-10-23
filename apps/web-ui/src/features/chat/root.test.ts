import { describe, expect, it } from 'vitest';
import { DEFAULT_ROOT, isValidRoot, MAX_ROOT_LENGTH } from './root';

const chars = (...codes: number[]) => String.fromCharCode(...codes);

describe('isValidRoot', () => {
    it('accepts the two roots and directories below them', () => {
        expect(isValidRoot(DEFAULT_ROOT)).toBe(true);
        expect(isValidRoot('/corpus')).toBe(true);
        expect(isValidRoot('/workspace/qbank-payment-service')).toBe(true);
        expect(isValidRoot('/workspace/a/b.c/d_e')).toBe(true);
        expect(isValidRoot('/workspace/çalışma')).toBe(true);
    });

    it('refuses anything outside /workspace and /corpus', () => {
        for (const root of ['', '/', '/etc', 'workspace', '/workspaces', '/workspace2/x', '/Workspace']) {
            expect(isValidRoot(root), root).toBe(false);
        }
    });

    it('refuses empty, "." and ".." segments, a trailing slash and a backslash', () => {
        for (const root of [
            '/workspace/',
            '/workspace//x',
            '/workspace/./x',
            '/workspace/../etc',
            '/workspace/x/..',
            '/workspace/x/',
            '/workspace\\x',
            '/workspace/a\\b',
        ]) {
            expect(isValidRoot(root), root).toBe(false);
        }
    });

    it('accepts names that merely contain dots', () => {
        expect(isValidRoot('/workspace/..a')).toBe(true);
        expect(isValidRoot('/workspace/a..')).toBe(true);
        expect(isValidRoot('/workspace/...')).toBe(true);
    });

    it('refuses control, invisible and direction characters', () => {
        const excluded = [
            0x00, 0x09, 0x0a, 0x1f, 0x7f, 0x85, 0x9f, 0xad, 0x200b, 0x200e, 0x202e, 0x2028, 0xfeff,
        ];
        for (const code of excluded) {
            expect(isValidRoot(`/workspace/a${chars(code)}b`), code.toString(16)).toBe(false);
        }
    });

    it('refuses a root above the length limit', () => {
        expect(isValidRoot(`/workspace/${'a'.repeat(MAX_ROOT_LENGTH)}`)).toBe(false);
        expect(isValidRoot(`/workspace/${'a'.repeat(MAX_ROOT_LENGTH - '/workspace/'.length)}`)).toBe(true);
    });
});
