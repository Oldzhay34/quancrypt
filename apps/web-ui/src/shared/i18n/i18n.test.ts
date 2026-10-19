import { describe, expect, it } from 'vitest';
import { en } from './en';
import { tr } from './tr';

describe('dictionaries', () => {
    it('have exactly the same keys in Turkish and English', () => {
        expect(Object.keys(en).sort()).toEqual(Object.keys(tr).sort());
    });

    it('have no empty text and use the same {placeholders} in both languages', () => {
        const placeholders = (text: string) =>
            [...text.matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort();
        for (const key of Object.keys(tr) as (keyof typeof tr)[]) {
            expect(tr[key].trim(), key).not.toBe('');
            expect(en[key].trim(), key).not.toBe('');
            expect(placeholders(en[key]), key).toEqual(placeholders(tr[key]));
        }
    });
});
