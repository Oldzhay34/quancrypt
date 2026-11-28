import { describe, expect, it } from 'vitest';
import { highlight, languageOf } from './highlight';

const kinds = (line: string, language: Parameters<typeof highlight>[1]) =>
    highlight(line, language)
        .filter((token) => token.kind !== 'plain')
        .map((token) => [token.kind, token.text]);

describe('code colouring', () => {
    it('names the language from the file ending', () => {
        expect(
            ['A.java', 'application.yml', 'a.properties', 'pom.xml', 'k.pem', 'notes'].map(languageOf),
        ).toEqual(['Java', 'YAML', 'Properties', 'XML', 'PEM', 'Text']);
    });

    it('marks keywords, strings, numbers and comments, and never loses a character', () => {
        const line = 'int size = 2048; Cipher.getInstance("RSA/ECB"); // old';
        expect(kinds(line, 'Java')).toEqual([
            ['keyword', 'int'],
            ['number', '2048'],
            ['string', '"RSA/ECB"'],
            ['comment', '// old'],
        ]);
        for (const sample of [line, '  * doc', 'a: "b"', 'key=value', '<x/>', '"unterminated']) {
            for (const language of ['Java', 'YAML', 'Properties', 'XML'] as const) {
                expect(
                    highlight(sample, language)
                        .map((token) => token.text)
                        .join(''),
                ).toBe(sample);
            }
        }
    });

    it('stays quick on a very long line', () => {
        const started = performance.now();
        highlight('"' + '\\\\'.repeat(2000) + 'a'.repeat(4000), 'Java');
        expect(performance.now() - started).toBeLessThan(500);
    });
});
