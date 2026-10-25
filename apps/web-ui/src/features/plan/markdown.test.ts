import { describe, expect, it } from 'vitest';
import { REPORT_TR } from '@/test/reviewFixtures';
import { parseMarkdown, splitRow, unescapeMarkdown } from './markdown';

describe('report markdown', () => {
    it('reads headings of three levels', () => {
        expect(parseMarkdown('# A\n\n## B\n\n### C')).toEqual([
            { type: 'heading', level: 1, text: 'A' },
            { type: 'heading', level: 2, text: 'B' },
            { type: 'heading', level: 3, text: 'C' },
        ]);
    });

    it('reads bullet lists and the numbered lines indented under an item', () => {
        const blocks = parseMarkdown('- one\n- two:\n  1. a: 1\n  2. b: 2\n- three\n  plain note');
        expect(blocks).toEqual([
            {
                type: 'list',
                items: [
                    { text: 'one', sub: [], ordered: false },
                    { text: 'two:', sub: ['a: 1', 'b: 2'], ordered: true },
                    { text: 'three', sub: ['plain note'], ordered: false },
                ],
            },
        ]);
    });

    it('reads tables, cell by cell, with escaped pipes kept inside the cell', () => {
        const [table] = parseMarkdown('| # | File |\n|---|---|\n| 1 | a\\|b.java |\n| 2 | c.java |');
        expect(table).toEqual({
            type: 'table',
            header: ['#', 'File'],
            rows: [
                ['1', 'a|b.java'],
                ['2', 'c.java'],
            ],
        });
        expect(splitRow('| x | y\\\\ |')).toEqual(['x', 'y\\']);
    });

    it('takes the backslash escapes of the service back, and only those', () => {
        expect(unescapeMarkdown('a\\_b \\*c\\* \\[d\\] \\<e\\> \\`f\\` \\\\g \\|h')).toBe(
            'a_b *c* [d] <e> `f` \\g |h',
        );
        expect(unescapeMarkdown('keep \\n and \\x')).toBe('keep \\n and \\x');
    });

    it('joins the lines of a paragraph and handles CRLF', () => {
        expect(parseMarkdown('one\r\ntwo\r\n\r\nthree')).toEqual([
            { type: 'paragraph', text: 'one two' },
            { type: 'paragraph', text: 'three' },
        ]);
    });

    it('keeps HTML, links and emphasis as plain text', () => {
        const [paragraph] = parseMarkdown('<script>alert(1)</script> [x](javascript:alert(1)) **bold**');
        expect(paragraph).toEqual({
            type: 'paragraph',
            text: '<script>alert(1)</script> [x](javascript:alert(1)) **bold**',
        });
    });

    it('reads a whole report in the order of its sections', () => {
        const blocks = parseMarkdown(REPORT_TR);
        const headings = blocks.flatMap((block) => (block.type === 'heading' ? [block.text] : []));
        expect(headings).toEqual([
            'Quancrypt geçiş planı raporu',
            '1. Özet',
            '2. Maddeler (riske göre sıralı)',
            '3. Madde ayrıntıları',
            '3.1. src/main/java/Pay3.java — Pay3#sign',
        ]);
        expect(blocks.filter((block) => block.type === 'table')).toHaveLength(1);
    });
});
