import { parseMarkdown } from '../markdown';
import type { Block } from '../markdown';
import styles from '../Plan.module.css';

function renderBlock(block: Block, index: number) {
    switch (block.type) {
        case 'heading':
            return block.level === 1 ? (
                <h2 key={index}>{block.text}</h2>
            ) : block.level === 2 ? (
                <h3 key={index}>{block.text}</h3>
            ) : (
                <h4 key={index}>{block.text}</h4>
            );
        case 'paragraph':
            return <p key={index}>{block.text}</p>;
        case 'list':
            return (
                <ul key={index}>
                    {block.items.map((item, itemIndex) => (
                        <li key={itemIndex}>
                            {item.text}
                            {item.sub.length === 0 ? null : item.ordered ? (
                                <ol>
                                    {item.sub.map((line, lineIndex) => (
                                        <li key={lineIndex}>{line}</li>
                                    ))}
                                </ol>
                            ) : (
                                <p>{item.sub.join(' ')}</p>
                            )}
                        </li>
                    ))}
                </ul>
            );
        case 'table':
            return (
                <div key={index} className={styles.tableWrap}>
                    <table className={styles.table}>
                        <thead>
                            <tr>
                                {block.header.map((cell, cellIndex) => (
                                    <th key={cellIndex} scope="col">
                                        {cell}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {block.rows.map((row, rowIndex) => (
                                <tr key={rowIndex}>
                                    {row.map((cell, cellIndex) => (
                                        <td key={cellIndex}>{cell}</td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            );
    }
}

/** The plan report as a document. Every piece of text is a React text node: nothing from the report is ever HTML. */
export function MarkdownView({ source }: { source: string }) {
    return <article className={styles.report}>{parseMarkdown(source).map(renderBlock)}</article>;
}
