/**
 * The analysis root rule of analyzer-service (contract `Root`, D-291f): `/workspace` or `/corpus`, or a directory below them,
 * with no empty, `.` or `..` segment, no backslash and none of the control, invisible or direction characters the contract
 * excludes. Checked here so a wrong root is explained before the request; the server checks it again.
 *
 * The contract's pattern is `^/(workspace|corpus)(/(?!\.\.?(/|$))[^/<excluded>\\]+)*$`. The excluded characters are listed here
 * as code point ranges (the same ones), so no invisible character has to sit in this source file.
 */
const EXCLUDED_RANGES: ReadonlyArray<readonly [number, number]> = [
    [0x0000, 0x001f], // C0 controls
    [0x007f, 0x009f], // DEL and C1 controls
    [0x00ad, 0x00ad], // soft hyphen
    [0x061c, 0x061c], // Arabic letter mark
    [0x180e, 0x180e], // Mongolian vowel separator
    [0x200b, 0x200f], // zero-width and direction marks
    [0x2028, 0x202e], // line and paragraph separators, embeddings and overrides
    [0x2060, 0x206f], // word joiner, invisible operators, deprecated format characters
    [0xfeff, 0xfeff], // byte order mark
    [0xfff9, 0xfffb], // interlinear annotation
];

export const DEFAULT_ROOT = '/workspace';
export const MAX_ROOT_LENGTH = 1024;
const BACKSLASH = 0x5c;

function isAllowedSegment(segment: string): boolean {
    if (segment === '' || segment === '.' || segment === '..') return false;
    for (let index = 0; index < segment.length; index++) {
        const code = segment.charCodeAt(index);
        if (code === BACKSLASH) return false;
        if (EXCLUDED_RANGES.some(([from, to]) => code >= from && code <= to)) return false;
    }
    return true;
}

export function isValidRoot(root: string): boolean {
    if (root.length > MAX_ROOT_LENGTH) return false;
    const prefix = ['/workspace', '/corpus'].find((candidate) => root.startsWith(candidate));
    if (prefix === undefined) return false;
    const rest = root.slice(prefix.length);
    if (rest === '') return true;
    if (!rest.startsWith('/')) return false;
    return rest
        .slice(1)
        .split('/')
        .every((segment) => isAllowedSegment(segment));
}
