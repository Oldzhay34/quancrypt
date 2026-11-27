import type { SessionSummary } from '@/shared/api/types';

/** Splits the list into the sessions active today (the browser's local day) and the older ones, keeping the order. */
export function groupSessions(sessions: SessionSummary[], now: Date) {
    const day = (value: Date) => value.toDateString();
    const today = sessions.filter((session) => day(new Date(session.last_message_at)) === day(now));
    return { today, earlier: sessions.filter((session) => !today.includes(session)) };
}
