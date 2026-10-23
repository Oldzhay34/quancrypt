import { describe, expect, it } from 'vitest';
import { createSseParser, readSseStream, SseError } from './sse';
import type { SseMessage } from './sse';

const WIRE =
    'event: token\ndata: {"text":"Merhaba"}\n\n' +
    ': keep-alive\n\n' +
    'event: evidence\ndata: {"a":1,\ndata: "b":2}\n\n' +
    'data: plain\n\n';

const EXPECTED: SseMessage[] = [
    { event: 'token', data: '{"text":"Merhaba"}' },
    { event: 'evidence', data: '{"a":1,\n"b":2}' },
    { event: 'message', data: 'plain' },
];

function parseAll(chunks: string[]): SseMessage[] {
    const parser = createSseParser();
    return chunks.flatMap((chunk) => parser.push(chunk));
}

describe('SSE parser', () => {
    it('reads events, joins data lines, ignores comments and defaults the name to "message"', () => {
        expect(parseAll([WIRE])).toEqual(EXPECTED);
    });

    it('gives the same events however the text is cut, at every offset', () => {
        for (let cut = 0; cut <= WIRE.length; cut++) {
            expect(parseAll([WIRE.slice(0, cut), WIRE.slice(cut)])).toEqual(EXPECTED);
        }
    });

    it('gives the same events when the text arrives one character at a time', () => {
        expect(parseAll([...WIRE])).toEqual(EXPECTED);
    });

    it('accepts CRLF and bare CR line ends, also when "\\r" and "\\n" arrive in different chunks', () => {
        const crlf = WIRE.replaceAll('\n', '\r\n');
        const cr = WIRE.replaceAll('\n', '\r');
        expect(parseAll([crlf])).toEqual(EXPECTED);
        expect(parseAll([cr])).toEqual(EXPECTED);
        for (let cut = 0; cut <= crlf.length; cut++) {
            expect(parseAll([crlf.slice(0, cut), crlf.slice(cut)])).toEqual(EXPECTED);
        }
    });

    it('drops one leading space after the colon and keeps the rest of the value', () => {
        expect(parseAll(['data:no-space\n\ndata:  two\n\n'])).toEqual([
            { event: 'message', data: 'no-space' },
            { event: 'message', data: ' two' },
        ]);
    });

    it('ignores id, retry and unknown fields', () => {
        expect(parseAll(['id: 7\nretry: 100\nfoo: bar\nevent: done\ndata: {}\n\n'])).toEqual([
            { event: 'done', data: '{}' },
        ]);
    });

    it('emits nothing for an event without data', () => {
        expect(parseAll(['event: token\n\n'])).toEqual([]);
    });

    it('drops a byte order mark at the very start only', () => {
        const bom = String.fromCharCode(0xfeff);
        expect(parseAll([`${bom}data: a\n\n`])).toEqual([{ event: 'message', data: 'a' }]);
        expect(parseAll(['data: a\n\n', `${bom}data: b\n\n`])).toEqual([
            { event: 'message', data: 'a' },
            // Not at the start any more: "<bom>data" is no known field name, so nothing is reported.
        ]);
    });

    it('leaves an event that no empty line closed unreported', () => {
        expect(parseAll(['data: a\n\ndata: unfinished\n'])).toEqual([{ event: 'message', data: 'a' }]);
    });

    it('refuses an event above the size limit', () => {
        const parser = createSseParser(100);
        expect(() => {
            for (let i = 0; i < 10; i++) parser.push(`data: ${'x'.repeat(30)}\n`);
        }).toThrow(SseError);
    });

    it('refuses an unterminated line above the size limit', () => {
        const parser = createSseParser(100);
        expect(() => parser.push('x'.repeat(101))).toThrow(SseError);
    });
});

function bodyOf(parts: Uint8Array[]): ReadableStream<Uint8Array> {
    return new ReadableStream<Uint8Array>({
        start(controller) {
            for (const part of parts) controller.enqueue(part);
            controller.close();
        },
    });
}

async function collect(body: ReadableStream<Uint8Array>, signal?: AbortSignal): Promise<SseMessage[]> {
    const out: SseMessage[] = [];
    for await (const message of readSseStream(body, signal)) out.push(message);
    return out;
}

describe('readSseStream', () => {
    const encoder = new TextEncoder();

    it('decodes a multi-byte character that is cut between two chunks', async () => {
        const bytes = encoder.encode('event: token\ndata: {"text":"ş€😀"}\n\n');
        for (let cut = 1; cut < bytes.length; cut++) {
            const body = bodyOf([bytes.slice(0, cut), bytes.slice(cut)]);
            expect(await collect(body)).toEqual([{ event: 'token', data: '{"text":"ş€😀"}' }]);
        }
    });

    it('ends silently when the signal is aborted, and the caller can tell by the signal', async () => {
        const controller = new AbortController();
        let cancelled = false;
        const body = new ReadableStream<Uint8Array>({
            start(c) {
                c.enqueue(encoder.encode('data: first\n\n'));
            },
            cancel() {
                cancelled = true;
            },
        });
        const seen: SseMessage[] = [];
        const reading = (async () => {
            for await (const message of readSseStream(body, controller.signal)) {
                seen.push(message);
                controller.abort();
            }
        })();
        await reading;
        expect(seen).toEqual([{ event: 'message', data: 'first' }]);
        expect(controller.signal.aborted).toBe(true);
        expect(cancelled).toBe(true);
    });

    it('does not read at all when the signal is already aborted', async () => {
        const controller = new AbortController();
        controller.abort();
        let cancelled = false;
        const body = new ReadableStream<Uint8Array>({
            pull() {
                // Never has data.
            },
            cancel() {
                cancelled = true;
            },
        });
        expect(await collect(body, controller.signal)).toEqual([]);
        expect(cancelled).toBe(true);
    });
});
