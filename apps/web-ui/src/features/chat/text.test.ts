import { describe, expect, it } from 'vitest';
import { isRefusalText, REFUSAL_TEXTS } from './refusal';
import { forgetSessionId, loadSessionId, saveSessionId } from './sessionStore';
import { hasUnverified, referenceLabel, safeHttpsUrl, splitUnverified } from './text';

describe('splitUnverified', () => {
    it('separates the marks of unverified claims from the text, in both languages', () => {
        expect(splitUnverified('RSA kullanılıyor [doğrulanamadı] ve 5 dosya [unverified].')).toEqual([
            { text: 'RSA kullanılıyor ', unverified: false },
            { text: '[doğrulanamadı]', unverified: true },
            { text: ' ve 5 dosya ', unverified: false },
            { text: '[unverified]', unverified: true },
            { text: '.', unverified: false },
        ]);
        expect(hasUnverified('a [unverified]')).toBe(true);
        expect(hasUnverified('a [verified]')).toBe(false);
    });

    it('returns plain text as one part and keeps markup as text', () => {
        expect(splitUnverified('<b>x</b>')).toEqual([{ text: '<b>x</b>', unverified: false }]);
        expect(splitUnverified('')).toEqual([]);
    });
});

describe('safeHttpsUrl', () => {
    it('lets only absolute https addresses without credentials through', () => {
        expect(safeHttpsUrl('https://openjdk.org/jeps/496')).toBe('https://openjdk.org/jeps/496');
        for (const reference of [
            'javascript:alert(1)',
            'data:text/html,x',
            'http://example.org/',
            '//example.org/x',
            '/relative/path',
            'https://user:pw@example.org/',
            'https://user@example.org/',
            'not a url',
        ]) {
            expect(safeHttpsUrl(reference), reference).toBeNull();
        }
    });

    it('labels an address by host and path and cuts a long label to 80 characters', () => {
        expect(referenceLabel('https://openjdk.org/jeps/496/')).toBe('openjdk.org/jeps/496');
        expect(referenceLabel('A.java:12')).toBe('A.java:12');
        expect(referenceLabel('x'.repeat(200))).toHaveLength(80);
    });
});

describe('refusal text', () => {
    it('is recognised word for word in both languages, also with surrounding white space', () => {
        for (const text of REFUSAL_TEXTS) {
            expect(isRefusalText(text)).toBe(true);
            expect(isRefusalText(`  ${text}\n`)).toBe(true);
        }
        expect(isRefusalText('Bahsettiğiniz şeyi anlamadım.')).toBe(false);
        expect(isRefusalText('')).toBe(false);
    });
});

describe('session store', () => {
    const project = '11111111-1111-4111-8111-111111111111';
    const session = '22222222-2222-4222-8222-222222222222';

    it('remembers a session per project and forgets it', () => {
        expect(loadSessionId(project)).toBeNull();
        saveSessionId(project, session);
        expect(window.localStorage.getItem(`chatSession:${project}`)).toBe(session);
        expect(loadSessionId(project)).toBe(session);
        expect(loadSessionId('33333333-3333-4333-8333-333333333333')).toBeNull();
        forgetSessionId(project);
        expect(loadSessionId(project)).toBeNull();
    });

    it('ignores a stored value that is not a UUID (it would end up in a URL path)', () => {
        window.localStorage.setItem(`chatSession:${project}`, '../../admin');
        expect(loadSessionId(project)).toBeNull();
    });
});
