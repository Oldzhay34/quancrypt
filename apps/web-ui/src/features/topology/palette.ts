import type { QuantumStatus } from './quantum';

/**
 * Okabe-Ito colours (safe for the common kinds of colour blindness). Colour is never the only signal: each status also has its own
 * line width and arrow shape in the graph, a text name in the legend and in the connection list. The same values are in
 * `Topology.module.css` for the legend swatches (CSP allows no inline style); a test keeps the two in step.
 */
export const STATUS_COLORS: Record<QuantumStatus, string> = {
    VULNERABLE: '#D55E00',
    RESISTANT: '#0072B2',
    MIXED: '#E69F00',
    SYMMETRIC_OR_HASH: '#009E73',
    UNKNOWN: '#767676',
};

/** The arrow and the width that go with a status, so the graph reads in greyscale too. */
export const STATUS_LINE: Record<QuantumStatus, { arrow: string; width: number }> = {
    VULNERABLE: { arrow: 'triangle', width: 4 },
    RESISTANT: { arrow: 'tee', width: 4 },
    MIXED: { arrow: 'diamond', width: 3 },
    SYMMETRIC_OR_HASH: { arrow: 'circle', width: 2 },
    UNKNOWN: { arrow: 'vee', width: 1.5 },
};

export const STATUSES: readonly QuantumStatus[] = [
    'VULNERABLE',
    'RESISTANT',
    'MIXED',
    'SYMMETRIC_OR_HASH',
    'UNKNOWN',
];
