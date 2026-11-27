import { describe, expect, it } from 'vitest';
import type { SessionSummary } from '@/shared/api/types';
import { groupSessions } from './sessionGroups';

const session = (id: string, last: Date): SessionSummary => ({
    id,
    language: 'tr',
    created_at: last.toISOString(),
    last_message_at: last.toISOString(),
    preview: id,
});

describe('grouping the chat list', () => {
    it('puts the local day of now under today and keeps the order', () => {
        const now = new Date(2026, 10, 27, 12, 0);
        const list = [
            session('a', new Date(2026, 10, 27, 0, 5)),
            session('b', new Date(2026, 10, 26, 23, 55)),
            session('c', new Date(2026, 10, 27, 11, 0)),
        ];

        const { today, earlier } = groupSessions(list, now);

        expect(today.map((s) => s.id)).toEqual(['a', 'c']);
        expect(earlier.map((s) => s.id)).toEqual(['b']);
    });
});
