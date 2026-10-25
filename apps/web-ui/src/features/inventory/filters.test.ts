import { describe, expect, it } from 'vitest';
import { FINDINGS } from '@/test/reviewFixtures';
import { emptyFilter, isFiltered, paginate, serverQuery, visible } from './filters';

describe('inventory filters', () => {
    it('asks the server for nothing when no filter is set', () => {
        expect(serverQuery(emptyFilter)).toEqual({});
        expect(isFiltered(emptyFilter)).toBe(false);
    });

    it('passes the four server-side filters on and leaves out the empty ones', () => {
        const query = serverQuery({
            ...emptyFilter,
            priority: 'P0',
            algorithmFamily: 'RSA',
            usageContext: 'SIGNATURE',
            locationKind: 'CODE',
        });
        expect(query).toEqual({
            priority: 'P0',
            algorithmFamily: 'RSA',
            usageContext: 'SIGNATURE',
            locationKind: 'CODE',
        });
        expect(serverQuery({ ...emptyFilter, algorithmFamily: 'AES' })).toEqual({ algorithmFamily: 'AES' });
    });

    it('turns "only test code" into the TEST_CODE location kind, over any chosen kind', () => {
        expect(serverQuery({ ...emptyFilter, tests: 'only' })).toEqual({ locationKind: 'TEST_CODE' });
        expect(serverQuery({ ...emptyFilter, tests: 'only', locationKind: 'CONFIG' })).toEqual({
            locationKind: 'TEST_CODE',
        });
    });

    it('leaves test code out on the client, because the contract takes one location kind', () => {
        expect(serverQuery({ ...emptyFilter, tests: 'exclude' })).toEqual({});
        const kept = visible(FINDINGS, { ...emptyFilter, tests: 'exclude' });
        expect(kept).toHaveLength(FINDINGS.length - 1);
        expect(kept.some((finding) => finding.locationKind === 'TEST_CODE')).toBe(false);
        expect(visible(FINDINGS, emptyFilter)).toHaveLength(FINDINGS.length);
        expect(visible(FINDINGS, { ...emptyFilter, tests: 'only' })).toHaveLength(FINDINGS.length);
    });

    it('knows when a filter is set', () => {
        expect(isFiltered({ ...emptyFilter, tests: 'exclude' })).toBe(true);
        expect(isFiltered({ ...emptyFilter, priority: 'P2' })).toBe(true);
    });

    it('pages a list and keeps the page inside the range', () => {
        const items = Array.from({ length: 60 }, (_, index) => index);
        expect(paginate(items, 0, 25)).toEqual({ items: items.slice(0, 25), page: 0, pages: 3 });
        expect(paginate(items, 2, 25).items).toEqual(items.slice(50));
        expect(paginate(items, 9, 25).page).toBe(2);
        expect(paginate(items, -1, 25).page).toBe(0);
        expect(paginate([], 0, 25)).toEqual({ items: [], page: 0, pages: 1 });
    });
});
