/**
 * Server-sent events over `fetch` (P5.3): `EventSource` cannot send an `Authorization` header, so the response body is read as a
 * stream and parsed here. The parser follows the WHATWG rules the service relies on: lines end with `\n`, `\r\n` or `\r`, an
 * empty line ends an event, a `:` line is a comment, several `data:` lines join with `\n`, a leading BOM is dropped, and an event
 * that is not closed by an empty line when the stream ends is discarded. `id` and `retry` are ignored (there is no reconnect:
 * a run is not resumable). An event or an unterminated line above `MAX_EVENT_CHARS` is refused, so a broken or hostile server
 * cannot grow the page's memory without bound.
 */

/** One event: its `event:` name (`message` when absent) and its `data:` lines. */
export interface SseMessage {
    event: string;
    data: string;
}

export class SseError extends Error {
    constructor(message: string) {
        super(message);
        this.name = 'SseError';
    }
}

/** Characters of one event (and of one unterminated line) the parser accepts: 1 MiB of text. */
export const MAX_EVENT_CHARS = 1_048_576;

export interface SseParser {
    /** Feeds text; returns the events completed by it, in order. Throws `SseError` above the size limit. */
    push(chunk: string): SseMessage[];
}

export function createSseParser(maxEventChars: number = MAX_EVENT_CHARS): SseParser {
    let pending = ''; // the text after the last line end
    let atStart = true; // a BOM is dropped only at the very start
    let skipLf = false; // the previous chunk ended with "\r": a "\n" opening this chunk belongs to it
    let eventName = '';
    let dataLines: string[] = [];
    let size = 0;

    const reset = () => {
        eventName = '';
        dataLines = [];
        size = 0;
    };

    function onLine(line: string, out: SseMessage[]): void {
        if (line === '') {
            if (dataLines.length > 0)
                out.push({ event: eventName === '' ? 'message' : eventName, data: dataLines.join('\n') });
            reset();
            return;
        }
        if (line.startsWith(':')) return;
        const colon = line.indexOf(':');
        const field = colon === -1 ? line : line.slice(0, colon);
        let value = colon === -1 ? '' : line.slice(colon + 1);
        if (value.startsWith(' ')) value = value.slice(1);
        size += line.length;
        if (size > maxEventChars) throw new SseError('event too large');
        if (field === 'event') eventName = value;
        else if (field === 'data') dataLines.push(value);
        // `id`, `retry` and unknown fields are ignored.
    }

    return {
        push(chunk: string): SseMessage[] {
            const out: SseMessage[] = [];
            let text = pending + chunk;
            pending = '';
            if (text === '') return out;
            if (atStart) {
                if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
                atStart = false;
                if (text === '') return out;
            }
            let start = 0;
            if (skipLf) {
                if (text[0] === '\n') start = 1;
                skipLf = false;
            }
            for (let i = start; i < text.length; i++) {
                const char = text[i];
                if (char !== '\n' && char !== '\r') continue;
                onLine(text.slice(start, i), out);
                if (char === '\r') {
                    if (text[i + 1] === '\n') i++;
                    else if (i + 1 === text.length) skipLf = true;
                }
                start = i + 1;
            }
            pending = text.slice(start);
            if (pending.length > maxEventChars) throw new SseError('line too large');
            return out;
        },
    };
}

/**
 * The events of a response body, as they arrive. UTF-8 characters may be split between two chunks. Cancelling `signal` cancels the
 * body and ends the iteration silently: the caller checks `signal.aborted` to tell a cancellation from the end of the stream.
 */
export async function* readSseStream(
    body: ReadableStream<Uint8Array>,
    signal?: AbortSignal,
): AsyncGenerator<SseMessage> {
    const reader = body.getReader();
    const decoder = new TextDecoder('utf-8');
    const parser = createSseParser();
    const cancel = () => void reader.cancel().catch(() => undefined);
    if (signal?.aborted) cancel();
    signal?.addEventListener('abort', cancel, { once: true });
    try {
        for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            for (const message of parser.push(decoder.decode(value, { stream: true }))) yield message;
        }
        const rest = decoder.decode();
        if (rest !== '') for (const message of parser.push(rest)) yield message;
    } finally {
        signal?.removeEventListener('abort', cancel);
        await reader.cancel().catch(() => undefined);
        reader.releaseLock();
    }
}
