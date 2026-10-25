import type { Finding, Plan, PlanItem, Scan, Topology } from '@/shared/api/types';
import { PROJECT } from './fakeBackend';
import type { ScanOverview } from './fakeBackend';

export const SCAN: Scan = {
    id: '33333333-3333-4333-8333-333333333333',
    projectId: PROJECT.id,
    status: 'COMPLETED',
    startedAt: '2026-10-24T10:00:00Z',
    completedAt: '2026-10-24T10:02:00Z',
    runtimeProfileSequenceNo: null,
};

const uuid = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;

export function finding(n: number, patch: Partial<Finding> = {}): Finding {
    return {
        id: uuid(n),
        scanId: SCAN.id,
        path: `src/main/java/Pay${n}.java`,
        symbol: `Pay${n}#sign`,
        algorithmFamily: 'RSA',
        usageContext: 'SIGNATURE',
        locationKind: 'CODE',
        priority: 'P1',
        keySizeBits: 2048,
        lineStart: 10 + n,
        lineEnd: 12 + n,
        confidence: 0.9,
        classifiedBy: 'STATIC',
        ...patch,
    };
}

/** Six findings: three vulnerable, one resistant, one hash, one in test code. */
export const FINDINGS: Finding[] = [
    finding(1, { algorithmFamily: 'RSA', usageContext: 'TLS_KEY_EXCHANGE', priority: 'P1' }),
    finding(2, {
        algorithmFamily: 'RSA',
        usageContext: 'CERTIFICATE',
        priority: 'P3',
        locationKind: 'CERTIFICATE_FILE',
        lineStart: null,
    }),
    finding(3, { algorithmFamily: 'SHA1', usageContext: 'SIGNATURE', priority: 'P0', keySizeBits: null }),
    finding(4, { algorithmFamily: 'ML_KEM', usageContext: 'KEY_AGREEMENT', priority: 'P2' }),
    finding(5, {
        algorithmFamily: 'RSA',
        usageContext: 'ENCRYPTION',
        priority: 'P1',
        locationKind: 'TEST_CODE',
    }),
    finding(6, {
        algorithmFamily: 'UNKNOWN',
        usageContext: 'TLS_SERVER_AUTH',
        priority: 'P3',
        classifiedBy: 'LLM',
    }),
];

export const TOPOLOGY: Topology = {
    scanId: SCAN.id,
    recordedAt: '2026-10-24T10:02:00Z',
    nodes: [
        { name: 'qbank-gateway', nodeKind: 'GATEWAY' },
        { name: 'qbank-payment-service', nodeKind: 'SERVICE' },
        { name: 'mosquitto', nodeKind: 'BROKER' },
        { name: 'terminal-001', nodeKind: 'DEVICE' },
    ],
    links: [
        {
            source: 'qbank-gateway',
            target: 'qbank-payment-service',
            protocol: 'HTTP',
            tls: true,
            mtls: true,
            callSites: [{ path: 'src/Gw.java', lineStart: 5, lineEnd: 6, locationKind: 'CODE' }],
            findingIds: [FINDINGS[0]?.id ?? '', FINDINGS[1]?.id ?? ''],
        },
        {
            source: 'terminal-001',
            target: 'mosquitto',
            protocol: 'MQTT',
            tls: true,
            mtls: false,
            callSites: [],
            findingIds: [FINDINGS[3]?.id ?? ''],
        },
        {
            source: 'qbank-payment-service',
            target: 'mosquitto',
            protocol: 'MQTT',
            tls: false,
            mtls: false,
            callSites: [],
            findingIds: [],
        },
    ],
};

export function overview(topology: Topology | null = TOPOLOGY): ScanOverview {
    return {
        scan: SCAN,
        summary: {
            scan: SCAN,
            runtimeProfile: null,
            findingCount: FINDINGS.length,
            countsByPriority: { P0: 1, P1: 2, P2: 1, P3: 2 },
            countsByAlgorithmFamily: { RSA: 3, SHA1: 1, ML_KEM: 1, UNKNOWN: 1 },
            countsByLocationKind: { CODE: 4, CERTIFICATE_FILE: 1, TEST_CODE: 1 },
        },
        topology,
    };
}

export const PLAN: Plan = {
    id: '44444444-4444-4444-8444-444444444444',
    scanId: SCAN.id,
    createdAt: '2026-10-24T10:05:00Z',
    itemCount: 3,
};

export function planItem(n: number, patch: Partial<PlanItem> = {}): PlanItem {
    return {
        id: `55555555-5555-4555-8555-${String(n).padStart(12, '0')}`,
        findingId: uuid(n),
        strategy: 'HYBRID_TLS_KEX',
        effort: 'M',
        riskScore: 0.5,
        riskClass: 'MEDIUM',
        state: 'PLANNED',
        version: 1,
        riskFactors: [],
        ...patch,
    };
}

/** Deliberately not in risk order: the screen sorts them. */
export const PLAN_ITEMS: PlanItem[] = [
    planItem(1, { riskScore: 0.475, riskClass: 'MEDIUM' }),
    planItem(3, {
        riskScore: 0.9,
        riskClass: 'CRITICAL',
        strategy: 'FIX_WEAK_CLASSIC',
        effort: 'S',
        riskFactors: [
            { featureName: 'weak_hash', shapValue: 0.31234 },
            { featureName: 'on_service_path', shapValue: 0.1 },
        ],
    }),
    planItem(2, {
        riskScore: 0.175,
        riskClass: 'LOW',
        state: 'APPROVED',
        version: 3,
        strategy: 'HYBRID_KEX_CLASSIC_CERT',
        effort: 'S',
    }),
];

export const REPORT_TR = [
    '# Quancrypt geçiş planı raporu',
    '',
    '## 1. Özet',
    '',
    '- Toplam madde: 3',
    '- Risk sınıfına göre: CRITICAL 1, HIGH 0, MEDIUM 1, LOW 1',
    '',
    '## 2. Maddeler (riske göre sıralı)',
    '',
    '| # | Dosya | Sembol |',
    '|---|---|---|',
    '| 1 | src/main/java/Pay3.java | Pay3#sign |',
    '| 2 | src/a\\|b.java | Pay1\\_x |',
    '',
    '## 3. Madde ayrıntıları',
    '',
    '### 3.1. src/main/java/Pay3.java — Pay3#sign',
    '',
    '- Strateji: FIX_WEAK_CLASSIC',
    '- Gerekçeler (SHAP):',
    '  1. weak_hash: 0.312340',
    '  2. on_service_path: 0.100000',
    '',
    '<script>alert(1)</script> düz metin',
    '',
].join('\n');

export const REPORT_EN = '# Quancrypt migration plan report\n\n## 1. Summary\n\n- Total items: 3\n';
