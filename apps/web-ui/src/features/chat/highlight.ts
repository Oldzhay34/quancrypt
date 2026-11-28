/**
 * A small line-by-line colouring for the code boxes (D-362c): keywords, strings, comments and numbers. It only splits
 * text into pieces; nothing is ever interpreted or put into the page as markup.
 */
export type TokenKind = 'plain' | 'keyword' | 'string' | 'comment' | 'number';

export interface Token {
    text: string;
    kind: TokenKind;
}

export type CodeLanguage = 'Java' | 'YAML' | 'Properties' | 'XML' | 'PEM' | 'Kotlin' | 'Gradle' | 'Text';

const EXTENSIONS: Record<string, CodeLanguage> = {
    java: 'Java',
    yml: 'YAML',
    yaml: 'YAML',
    properties: 'Properties',
    conf: 'Properties',
    xml: 'XML',
    pem: 'PEM',
    crt: 'PEM',
    kt: 'Kotlin',
    kts: 'Gradle',
    gradle: 'Gradle',
};

export function languageOf(path: string): CodeLanguage {
    const extension = path.slice(path.lastIndexOf('.') + 1).toLowerCase();
    return EXTENSIONS[extension] ?? 'Text';
}

const JAVA_WORDS = new Set(
    (
        'abstract assert boolean break byte case catch char class const continue default do double else enum extends final ' +
        'finally float for goto if implements import instanceof int interface long native new package private protected ' +
        'public record return short static strictfp super switch synchronized this throw throws transient try var void ' +
        'volatile while yield true false null fun val object when'
    ).split(' '),
);

// Each alternative starts with a different character, so the scan stays linear on long lines.
const PIECES =
    /("(?:[^"\\]|\\.)*"?)|('(?:[^'\\]|\\.)*'?)|(\/\/.*$)|(\/\*.*?(?:\*\/|$))|(\d+(?:\.\d+)?)|([A-Za-z_$][A-Za-z0-9_$]*)/g;

function code(line: string): Token[] {
    const trimmed = line.trimStart();
    if (trimmed.startsWith('*') || trimmed.startsWith('/*')) return [{ text: line, kind: 'comment' }];
    const tokens: Token[] = [];
    let at = 0;
    for (const match of line.matchAll(PIECES)) {
        const [text, double, single, lineComment, blockComment, number, word] = match;
        const start = match.index;
        if (start > at) tokens.push({ text: line.slice(at, start), kind: 'plain' });
        const kind: TokenKind =
            double || single
                ? 'string'
                : lineComment || blockComment
                  ? 'comment'
                  : number
                    ? 'number'
                    : word && JAVA_WORDS.has(word)
                      ? 'keyword'
                      : 'plain';
        tokens.push({ text, kind });
        at = start + text.length;
    }
    if (at < line.length) tokens.push({ text: line.slice(at), kind: 'plain' });
    return tokens;
}

function config(line: string, separator: RegExp): Token[] {
    if (line.trimStart().startsWith('#')) return [{ text: line, kind: 'comment' }];
    const at = line.search(separator);
    if (at < 0) return [{ text: line, kind: 'plain' }];
    return [
        { text: line.slice(0, at), kind: 'keyword' },
        { text: line.slice(at, at + 1), kind: 'plain' },
        { text: line.slice(at + 1), kind: 'string' },
    ];
}

export function highlight(line: string, language: CodeLanguage): Token[] {
    if (language === 'Java' || language === 'Kotlin' || language === 'Gradle') return code(line);
    if (language === 'YAML') return config(line, /:/);
    if (language === 'Properties') return config(line, /[=:]/);
    return [{ text: line, kind: 'plain' }];
}
