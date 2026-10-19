import { afterEach, describe, expect, it } from 'vitest';
import { acquireToken, clearStoredToken, isValidToken } from './token';

const TOKEN = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNO_-';

afterEach(() => {
    window.history.replaceState(null, '', '/');
});

describe('session token', () => {
    it('has the shape quancrypt init makes (43 base64url characters)', () => {
        expect(TOKEN).toHaveLength(43);
        expect(isValidToken(TOKEN)).toBe(true);
        expect(isValidToken('short')).toBe(false);
        expect(isValidToken(`${TOKEN}=`)).toBe(false);
        expect(isValidToken(null)).toBe(false);
    });

    it('is read from the fragment and the fragment leaves the address bar at once', () => {
        window.history.replaceState(null, '', `/chat?x=1#token=${TOKEN}`);

        expect(acquireToken()).toBe(TOKEN);
        expect(window.location.hash).toBe('');
        expect(window.location.pathname + window.location.search).toBe('/chat?x=1');
    });

    it('is kept in sessionStorage for a reload, and cleared on request', () => {
        window.history.replaceState(null, '', `/#token=${TOKEN}`);
        acquireToken();
        expect(window.sessionStorage.getItem('quancrypt.session')).toBe(TOKEN);

        expect(acquireToken()).toBe(TOKEN);
        clearStoredToken();
        expect(acquireToken()).toBeNull();
        expect(window.sessionStorage.getItem('quancrypt.session')).toBeNull();
    });

    it('discards an invalid fragment value and still removes it from the address bar', () => {
        window.history.replaceState(null, '', '/#token=not-a-token');

        expect(acquireToken()).toBeNull();
        expect(window.location.hash).toBe('');
        expect(window.sessionStorage.getItem('quancrypt.session')).toBeNull();
    });

    it('is never taken from a stored value of the wrong shape', () => {
        window.sessionStorage.setItem('quancrypt.session', 'tampered');

        expect(acquireToken()).toBeNull();
    });

    it('survives a browser that blocks sessionStorage (memory only)', () => {
        const original = Storage.prototype.setItem;
        Storage.prototype.setItem = () => {
            throw new Error('blocked');
        };
        try {
            window.history.replaceState(null, '', `/#token=${TOKEN}`);
            expect(acquireToken()).toBe(TOKEN);
            expect(acquireToken()).toBe(TOKEN);
        } finally {
            Storage.prototype.setItem = original;
        }
    });
});
