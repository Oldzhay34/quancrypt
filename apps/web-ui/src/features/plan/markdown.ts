/**
 * A small Markdown reader for the plan report of core-service (`PlanReportRenderer`, D-164): headings (`#` to `###`), bullet lists
 * with indented lines, tables, paragraphs and the backslash escapes the service puts before `\ ` * _ [ ] < > |` in names. It reads
 * nothing else: no HTML, no links, no emphasis, so a name from a project can never become markup. What it does not know stays text.
 */
export interface ListItem {
    text: string;
    /** The lines indented under the item; `ordered` when they are numbered ("1. ..."). */
    sub: string[];
    ordered: boolean;
}

export type Block =
    | { type: 'heading'; level: 1 | 2 | 3; text: string }
    | { type: 'list'; items: ListItem[] }
    | { type: 'table'; header: string[]; rows: string[][] }
    | { type: 'paragraph'; text: string };

const ESCAPED = /\\([\\`*_[\]<>|])/g;

export function unescapeMarkdown(text: string): string {
    return text.replace(ESCAPED, '$1');
}

/** Splits a table line at the pipes that are not escaped; the outer pipes are not cells. */
export function splitRow(line: string): string[] {
    const cells: string[] = [];
    let current = '';
    for (let index = 0; index < line.length; index++) {
        const char = line.charAt(index);
        if (char === '\\' && index + 1 < line.length) {
            current += char + line.charAt(index + 1);
            index++;
        } else if (char === '|') {
            cells.push(current);
            current = '';
        } else {
            current += char;
        }
    }
    cells.push(current);
    const trimmed = line.trim();
    if (trimmed.startsWith('|')) cells.shift();
    if (trimmed.endsWith('|') && !trimmed.endsWith('\\|')) cells.pop();
    return cells.map((cell) => unescapeMarkdown(cell.trim()));
}

const SEPARATOR = /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/;
const HEADING = /^(#{1,3}) (.*)$/;
const NUMBERED = /^\s+\d+\.\s+(.*)$/;

export function parseMarkdown(source: string): Block[] {
    const lines = source.replace(/\r\n?/g, '\n').split('\n');
    const blocks: Block[] = [];
    let index = 0;
    while (index < lines.length) {
        const line = lines[index] ?? '';
        if (line.trim() === '') {
            index++;
            continue;
        }
        const heading = HEADING.exec(line);
        if (heading) {
            blocks.push({
                type: 'heading',
                level: (heading[1] ?? '#').length as 1 | 2 | 3,
                text: unescapeMarkdown((heading[2] ?? '').trim()),
            });
            index++;
            continue;
        }
        if (line.startsWith('|') && SEPARATOR.test((lines[index + 1] ?? '').trim())) {
            const header = splitRow(line);
            const rows: string[][] = [];
            index += 2;
            while (index < lines.length && (lines[index] ?? '').startsWith('|')) {
                rows.push(splitRow(lines[index] ?? ''));
                index++;
            }
            blocks.push({ type: 'table', header, rows });
            continue;
        }
        if (line.startsWith('- ')) {
            const items: ListItem[] = [];
            while (index < lines.length && (lines[index] ?? '').startsWith('- ')) {
                const item: ListItem = {
                    text: unescapeMarkdown((lines[index] ?? '').slice(2).trim()),
                    sub: [],
                    ordered: false,
                };
                index++;
                while (index < lines.length && /^ {2,}\S/.test(lines[index] ?? '')) {
                    const numbered = NUMBERED.exec(lines[index] ?? '');
                    if (numbered) item.ordered = true;
                    item.sub.push(
                        unescapeMarkdown((numbered ? (numbered[1] ?? '') : (lines[index] ?? '')).trim()),
                    );
                    index++;
                }
                items.push(item);
            }
            blocks.push({ type: 'list', items });
            continue;
        }
        const paragraph: string[] = [];
        while (
            index < lines.length &&
            (lines[index] ?? '').trim() !== '' &&
            !HEADING.test(lines[index] ?? '') &&
            !(lines[index] ?? '').startsWith('- ') &&
            !(lines[index] ?? '').startsWith('|')
        ) {
            paragraph.push((lines[index] ?? '').trim());
            index++;
        }
        if (paragraph.length === 0) {
            // A line that starts a block we do not know ("|" without a separator): keep it as text and move on.
            paragraph.push((lines[index] ?? '').trim());
            index++;
        }
        blocks.push({ type: 'paragraph', text: unescapeMarkdown(paragraph.join(' ')) });
    }
    return blocks;
}
