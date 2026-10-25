import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { getTopology, useApi } from '@/shared/api';
import { useScanFindings } from '@/shared/scan';
import { buildGraph } from './graph';

/** The recorded topology of a scan with its findings, as a graph and a connection list; `topology` is null when none was recorded. */
export function useTopologyGraph(scanId: string) {
    const api = useApi();
    const topology = useQuery({
        queryKey: ['scan', scanId, 'topology'],
        queryFn: ({ signal }) => getTopology(api, scanId, signal),
    });
    const findings = useScanFindings(scanId);
    const graph = useMemo(
        () => (topology.data && findings.data ? buildGraph(topology.data, findings.data) : null),
        [topology.data, findings.data],
    );
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const selected = graph?.connections.find((connection) => connection.id === selectedId) ?? null;
    return { topology, findings, graph, selected, selectedId, setSelectedId };
}
