/** Small pure helpers for rendering answers and evidence. */

export interface TextPart {
    text: string;
    unverified: boolean;
}

/** The marks the service's output checker puts after a claim it could not verify (`on_mismatch: flag`). */
const UNVERIFIED = /\[(?:doğrulanamadı|unverified)\]/g;

/** Splits an answer at its "[doğrulanamadı]" / "[unverified]" marks so they can be shown apart. Text only: never HTML. */
export function splitUnverified(text: string): TextPart[] {
    const parts: TextPart[] = [];
    let last = 0;
    for (const match of text.matchAll(UNVERIFIED)) {
        const at = match.index;
        if (at > last) parts.push({ text: text.slice(last, at), unverified: false });
        parts.push({ text: match[0], unverified: true });
        last = at + match[0].length;
    }
    if (last < text.length) parts.push({ text: text.slice(last), unverified: false });
    return parts;
}

export function hasUnverified(text: string): boolean {
    return new RegExp(UNVERIFIED.source).test(text);
}

/**
 * A knowledge-base reference becomes a link only when it is an absolute `https:` address without credentials: `javascript:`,
 * `data:`, plain `http:` and relative values stay text. (The database allows only `https://` sources; the check does not rely on it.)
 */
export function safeHttpsUrl(reference: string): string | null {
    try {
        const url = new URL(reference);
        if (url.protocol !== 'https:' || url.username !== '' || url.password !== '') return null;
        return url.href;
    } catch {
        return null;
    }
}

const LABEL_MAX = 80;

/** What a chip shows for a reference: host and path of an address, otherwise the reference as it is; at most 80 characters. */
export function referenceLabel(reference: string): string {
    const url = safeHttpsUrl(reference);
    const label = url === null ? reference : new URL(url).host + new URL(url).pathname.replace(/\/$/, '');
    return label.length > LABEL_MAX ? `${label.slice(0, LABEL_MAX - 1)}…` : label;
}
