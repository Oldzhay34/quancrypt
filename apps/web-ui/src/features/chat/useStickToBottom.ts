import { useCallback, useLayoutEffect, useRef } from 'react';

/** How close to the end still counts as "at the end". */
const SLACK_PX = 80;

/** Keeps a scrolling area at its end while new content arrives, unless the reader scrolled up. */
export function useStickToBottom(...changes: unknown[]) {
    const ref = useRef<HTMLDivElement>(null);
    const atEnd = useRef(true);
    const onScroll = useCallback(() => {
        const area = ref.current;
        if (area) atEnd.current = area.scrollHeight - area.scrollTop - area.clientHeight < SLACK_PX;
    }, []);
    useLayoutEffect(() => {
        const area = ref.current;
        if (area && atEnd.current) area.scrollTop = area.scrollHeight;
        // The caller names what makes the content grow.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, changes);
    return { ref, onScroll };
}
