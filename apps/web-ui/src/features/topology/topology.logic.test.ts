import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import type { AlgorithmFamily } from '@/shared/api/types';
import { FINDINGS, TOPOLOGY } from '@/test/reviewFixtures';
import { buildGraph, NODE_SHAPES } from './graph';
import { STATUS_COLORS, STATUS_LINE, STATUSES } from './palette';
import { edgeStatus, familyStatus } from './quantum';

const of = (...families: AlgorithmFamily[]) => families.map((algorithmFamily) => ({ algorithmFamily }));

describe('quantum status', () => {
    it('maps the algorithm families as crypto-domain does', () => {
        for (const family of ['RSA', 'ECDSA', 'ECDH', 'EDDSA', 'DH', 'DSA', 'X25519'] as const) {
            expect(familyStatus(family), family).toBe('VULNERABLE');
        }
        for (const family of ['ML_KEM', 'ML_DSA', 'SLH_DSA', 'HYBRID_X25519_MLKEM768'] as const) {
            expect(familyStatus(family), family).toBe('RESISTANT');
        }
        for (const family of [
            'AES',
            'DES',
            'TRIPLE_DES',
            'CHACHA20',
            'SHA1',
            'SHA2',
            'SHA3',
            'MD5',
            'HMAC',
        ] as const) {
            expect(familyStatus(family), family).toBe('SYMMETRIC_OR_HASH');
        }
        expect(familyStatus('UNKNOWN')).toBe('UNKNOWN');
    });

    it('derives the status of a connection from its findings', () => {
        expect(edgeStatus(of('RSA'))).toBe('VULNERABLE');
        expect(edgeStatus(of('RSA', 'AES', 'UNKNOWN'))).toBe('VULNERABLE');
        expect(edgeStatus(of('ML_KEM'))).toBe('RESISTANT');
        expect(edgeStatus(of('ML_KEM', 'AES'))).toBe('RESISTANT');
        expect(edgeStatus(of('RSA', 'HYBRID_X25519_MLKEM768'))).toBe('MIXED');
        expect(edgeStatus(of('SHA2', 'AES'))).toBe('SYMMETRIC_OR_HASH');
        expect(edgeStatus(of('UNKNOWN'))).toBe('UNKNOWN');
        expect(edgeStatus([])).toBe('UNKNOWN');
    });
});

describe('graph elements', () => {
    const graph = buildGraph(TOPOLOGY, FINDINGS);

    it('has one node per recorded node, with its kind', () => {
        expect(graph.nodes.map((node) => [node.data.label, node.data.kind])).toEqual([
            ['qbank-gateway', 'GATEWAY'],
            ['qbank-payment-service', 'SERVICE'],
            ['mosquitto', 'BROKER'],
            ['terminal-001', 'DEVICE'],
        ]);
    });

    it('keeps ids unique and apart even when a node is named like an edge id', () => {
        const hostile = buildGraph(
            {
                ...TOPOLOGY,
                nodes: [
                    { name: 'e:0', nodeKind: 'SERVICE' },
                    { name: 'n:1', nodeKind: 'SERVICE' },
                    { name: 'edge-0', nodeKind: 'GATEWAY' },
                ],
                links: [
                    {
                        source: 'e:0',
                        target: 'edge-0',
                        protocol: 'HTTP',
                        tls: true,
                        mtls: false,
                        callSites: [],
                        findingIds: [],
                    },
                ],
            },
            FINDINGS,
        );
        const ids = [...hostile.nodes, ...hostile.edges].map((element) => element.data.id);
        expect(new Set(ids).size).toBe(ids.length);
        expect(hostile.edges).toHaveLength(1);
        // The edge joins the node ids of the two names, and the connection still shows the names.
        const [edge] = hostile.edges;
        expect(hostile.nodes.find((node) => node.data.id === edge?.data.source)?.data.label).toBe('e:0');
        expect(hostile.nodes.find((node) => node.data.id === edge?.data.target)?.data.label).toBe('edge-0');
        expect(hostile.connections[0]?.source).toBe('e:0');
    });

    it('gives every node kind its own shape', () => {
        const shapes = Object.values(NODE_SHAPES);
        expect(new Set(shapes).size).toBe(shapes.length);
    });

    it('colours each edge by the findings linked to it and labels it with protocol and transport security', () => {
        expect(graph.edges.map((edge) => [edge.data.label, edge.data.status])).toEqual([
            ['HTTP mTLS', 'VULNERABLE'],
            ['MQTT TLS', 'RESISTANT'],
            ['MQTT', 'UNKNOWN'],
        ]);
    });

    it('lists the connections with their findings for the side panel', () => {
        const first = graph.connections[0];
        expect(first?.source).toBe('qbank-gateway');
        expect(first?.findings.map((finding) => finding.id)).toEqual([FINDINGS[0]?.id, FINDINGS[1]?.id]);
        expect(first?.callSiteCount).toBe(1);
        expect(graph.connections[2]?.findings).toEqual([]);
    });

    it('leaves out a connection whose end is not a recorded node, and ignores unknown finding ids', () => {
        const odd = buildGraph(
            {
                ...TOPOLOGY,
                links: [
                    { ...(TOPOLOGY.links[0] as (typeof TOPOLOGY.links)[number]), target: 'nowhere' },
                    { ...(TOPOLOGY.links[1] as (typeof TOPOLOGY.links)[number]), findingIds: ['missing'] },
                ],
            },
            FINDINGS,
        );
        expect(odd.edges).toHaveLength(1);
        expect(odd.connections[0]?.findings).toEqual([]);
        expect(odd.connections[0]?.status).toBe('UNKNOWN');
    });
});

describe('colours and legend', () => {
    it('gives every status a colour, an arrow and a width of its own, so colour is never the only signal', () => {
        const arrows = STATUSES.map((status) => STATUS_LINE[status].arrow);
        expect(new Set(arrows).size).toBe(STATUSES.length);
        const colours = STATUSES.map((status) => STATUS_COLORS[status].toLowerCase());
        expect(new Set(colours).size).toBe(STATUSES.length);
    });

    it('uses the Okabe-Ito colours for the vulnerable and resistant statuses', () => {
        expect(STATUS_COLORS.VULNERABLE).toBe('#D55E00');
        expect(STATUS_COLORS.RESISTANT).toBe('#0072B2');
    });

    it('keeps the legend swatches (CSS) in step with the graph colours (TS)', () => {
        const css = readFileSync('src/features/topology/Topology.module.css', 'utf8');
        for (const colour of Object.values(STATUS_COLORS)) {
            expect(css.toLowerCase(), colour).toContain(colour.toLowerCase());
        }
    });
});
