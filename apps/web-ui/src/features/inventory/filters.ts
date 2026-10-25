import type { FindingQuery } from '@/shared/api';
import type { AlgorithmFamily, Finding, LocationKind, Priority, UsageContext } from '@/shared/api/types';

/** The code lists of the contract (crypto-domain), in the order the filter menus show them. */
export const PRIORITIES: readonly Priority[] = ['P0', 'P1', 'P2', 'P3'];
export const ALGORITHM_FAMILIES: readonly AlgorithmFamily[] = [
    'RSA',
    'ECDSA',
    'ECDH',
    'EDDSA',
    'DH',
    'DSA',
    'ML_KEM',
    'ML_DSA',
    'SLH_DSA',
    'AES',
    'DES',
    'TRIPLE_DES',
    'CHACHA20',
    'SHA1',
    'SHA2',
    'SHA3',
    'MD5',
    'HMAC',
    'X25519',
    'HYBRID_X25519_MLKEM768',
    'UNKNOWN',
];
export const USAGE_CONTEXTS: readonly UsageContext[] = [
    'TLS_KEY_EXCHANGE',
    'TLS_SERVER_AUTH',
    'MTLS_CLIENT_AUTH',
    'CERTIFICATE',
    'ENCRYPTION',
    'KEY_WRAP',
    'SIGNATURE',
    'TOKEN_SIGNATURE',
    'KEY_AGREEMENT',
    'HASH',
    'SYMMETRIC_ENCRYPTION',
    'KEYSTORE',
    'UNKNOWN',
];
export const LOCATION_KINDS: readonly LocationKind[] = [
    'CODE',
    'CONFIG',
    'CERTIFICATE_FILE',
    'KEYSTORE_FILE',
    'BUILD_FILE',
    'TEST_CODE',
];

/** Test code: shown with everything else, only test code, or left out. */
export type TestMode = 'include' | 'only' | 'exclude';

export interface FindingFilter {
    priority: Priority | '';
    algorithmFamily: AlgorithmFamily | '';
    usageContext: UsageContext | '';
    locationKind: LocationKind | '';
    tests: TestMode;
}

export const emptyFilter: FindingFilter = {
    priority: '',
    algorithmFamily: '',
    usageContext: '',
    locationKind: '',
    tests: 'include',
};

export const PAGE_SIZE = 25;

/**
 * What `ListFindings` filters by itself. "Only test code" is the `TEST_CODE` location kind and overrides the kind menu; leaving
 * test code out has no server filter (the contract takes one location kind), so `visible` does it.
 */
export function serverQuery(filter: FindingFilter): FindingQuery {
    const query: FindingQuery = {};
    if (filter.priority) query.priority = filter.priority;
    if (filter.algorithmFamily) query.algorithmFamily = filter.algorithmFamily;
    if (filter.usageContext) query.usageContext = filter.usageContext;
    const kind = filter.tests === 'only' ? 'TEST_CODE' : filter.locationKind;
    if (kind) query.locationKind = kind;
    return query;
}

/** The findings that pass the part of the filter the server cannot do. */
export function visible(findings: readonly Finding[], filter: FindingFilter): Finding[] {
    if (filter.tests === 'exclude') return findings.filter((finding) => finding.locationKind !== 'TEST_CODE');
    return [...findings];
}

/** One page (counting from 0) of a list, and how many pages there are (at least 1). */
export function paginate<T>(items: readonly T[], page: number, size: number = PAGE_SIZE) {
    const pages = Math.max(1, Math.ceil(items.length / size));
    const current = Math.min(Math.max(0, page), pages - 1);
    return { items: items.slice(current * size, (current + 1) * size), page: current, pages };
}

export function isFiltered(filter: FindingFilter): boolean {
    return (Object.keys(emptyFilter) as (keyof FindingFilter)[]).some(
        (key) => filter[key] !== emptyFilter[key],
    );
}
