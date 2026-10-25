import type { Finding, Topology } from '@/shared/api/types';
import { edgeStatus } from './quantum';
import type { QuantumStatus } from './quantum';

export type NodeKind = Topology['nodes'][number]['nodeKind'];

/** The node shape per kind (Cytoscape shape names): service, gateway, broker, device and outside client differ by shape. */
export const NODE_SHAPES: Record<NodeKind, string> = {
    SERVICE: 'round-rectangle',
    GATEWAY: 'diamond',
    BROKER: 'hexagon',
    DEVICE: 'barrel',
    EXTERNAL_CLIENT: 'ellipse',
};

export interface GraphNode {
    data: { id: string; label: string; kind: NodeKind };
}

export interface GraphEdge {
    data: {
        id: string;
        source: string;
        target: string;
        label: string;
        status: QuantumStatus;
        protocol: string;
        tls: boolean;
        mtls: boolean;
    };
}

/** A connection with what the side panel shows about it. */
export interface Connection {
    id: string;
    source: string;
    target: string;
    protocol: string;
    tls: boolean;
    mtls: boolean;
    status: QuantumStatus;
    callSiteCount: number;
    findings: Finding[];
}

export interface TopologyGraph {
    nodes: GraphNode[];
    edges: GraphEdge[];
    connections: Connection[];
}

function edgeLabel(protocol: string, tls: boolean, mtls: boolean): string {
    return mtls ? `${protocol} mTLS` : tls ? `${protocol} TLS` : protocol;
}

/** Cytoscape elements and the connection list from a recorded topology and the scan's findings. */
export function buildGraph(topology: Topology, findings: readonly Finding[]): TopologyGraph {
    const byId = new Map(findings.map((finding) => [finding.id, finding]));
    // Names come from the analysed project and may be anything (even "e:0"): Cytoscape ids are made here, in two separate
    // series, and the name only serves as the label. A repeated id would make Cytoscape drop the element silently.
    const nodes = topology.nodes.map((node, index) => ({
        data: { id: `n:${index}`, label: node.name, kind: node.nodeKind },
    }));
    const nodeIds = new Map<string, string>();
    topology.nodes.forEach((node, index) => {
        if (!nodeIds.has(node.name)) nodeIds.set(node.name, `n:${index}`);
    });
    const edges: GraphEdge[] = [];
    const connections: Connection[] = [];
    topology.links.forEach((link, index) => {
        // A link whose end is not a recorded node cannot be drawn.
        const source = nodeIds.get(link.source);
        const target = nodeIds.get(link.target);
        if (source === undefined || target === undefined) return;
        const linked = link.findingIds.flatMap((id) => {
            const finding = byId.get(id);
            return finding ? [finding] : [];
        });
        const id = `e:${index}`;
        const status = edgeStatus(linked);
        edges.push({
            data: {
                id,
                source,
                target,
                label: edgeLabel(link.protocol, link.tls, link.mtls),
                status,
                protocol: link.protocol,
                tls: link.tls,
                mtls: link.mtls,
            },
        });
        connections.push({
            id,
            source: link.source,
            target: link.target,
            protocol: link.protocol,
            tls: link.tls,
            mtls: link.mtls,
            status,
            callSiteCount: link.callSites.length,
            findings: linked,
        });
    });
    return { nodes, edges, connections };
}
