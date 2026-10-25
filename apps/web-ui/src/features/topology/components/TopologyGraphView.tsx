import cytoscape from 'cytoscape';
import { useEffect, useRef } from 'react';
import { NODE_SHAPES } from '../graph';
import type { NodeKind, TopologyGraph } from '../graph';
import { STATUS_COLORS, STATUS_LINE, STATUSES } from '../palette';
import styles from '../Topology.module.css';

function styleSheet(text: string, background: string): cytoscape.StylesheetJson {
    const kinds = Object.keys(NODE_SHAPES) as NodeKind[];
    return [
        {
            selector: 'node',
            style: {
                label: 'data(label)',
                color: text,
                'font-size': 12,
                'text-valign': 'bottom',
                'text-margin-y': 6,
                'background-color': background,
                'border-width': 2,
                'border-color': text,
                width: 44,
                height: 44,
            },
        },
        ...kinds.map((kind) => ({
            selector: `node[kind = "${kind}"]`,
            style: { shape: NODE_SHAPES[kind] as cytoscape.Css.NodeShape },
        })),
        {
            selector: 'edge',
            style: {
                label: 'data(label)',
                color: text,
                'font-size': 10,
                'curve-style': 'bezier',
                'text-background-color': background,
                'text-background-opacity': 0.85,
                'text-background-padding': '2px',
                'target-arrow-fill': 'filled',
            },
        },
        ...STATUSES.map((status) => ({
            selector: `edge[status = "${status}"]`,
            style: {
                'line-color': STATUS_COLORS[status],
                'target-arrow-color': STATUS_COLORS[status],
                'target-arrow-shape': STATUS_LINE[status].arrow as cytoscape.Css.ArrowShape,
                width: STATUS_LINE[status].width,
            },
        })),
        {
            selector: 'edge:selected',
            style: { 'overlay-color': text, 'overlay-opacity': 0.18, 'overlay-padding': 6 },
        },
    ] as cytoscape.StylesheetJson;
}

interface TopologyGraphViewProps {
    graph: TopologyGraph;
    selectedId: string | null;
    onSelect: (edgeId: string | null) => void;
    /** The accessible name of the picture; the connection list next to it holds the same information as text. */
    label: string;
}

/**
 * The service graph (Cytoscape.js). Styles are Cytoscape's own (drawn on a canvas), so the page needs no inline style. A tap on a
 * connection selects it; a tap on empty space clears the selection. The graph is rebuilt only when the data changes.
 */
export function TopologyGraphView({ graph, selectedId, onSelect, label }: TopologyGraphViewProps) {
    const container = useRef<HTMLDivElement>(null);
    const cy = useRef<cytoscape.Core | null>(null);
    const selectRef = useRef(onSelect);

    useEffect(() => {
        selectRef.current = onSelect;
    }, [onSelect]);

    useEffect(() => {
        const root = getComputedStyle(document.documentElement);
        const text = root.getPropertyValue('--text').trim() || '#1b1f24';
        const background = root.getPropertyValue('--surface').trim() || '#ffffff';
        const instance = cytoscape({
            container: container.current,
            elements: [...graph.nodes, ...graph.edges],
            style: styleSheet(text, background),
            layout: { name: 'breadthfirst', directed: true, padding: 24, spacingFactor: 1.5 },
            boxSelectionEnabled: false,
            autounselectify: false,
        });
        instance.on('tap', 'edge', (event) => selectRef.current(event.target.id()));
        instance.on('tap', (event) => {
            if (event.target === instance) selectRef.current(null);
        });
        // The canvas does not follow its container by itself: when the side panel opens or the window changes, fit the graph again.
        const observed = container.current;
        const observer =
            typeof ResizeObserver === 'undefined' || observed === null
                ? null
                : new ResizeObserver(() => {
                      instance.resize();
                      instance.fit(undefined, 24);
                  });
        if (observer && observed) observer.observe(observed);
        cy.current = instance;
        return () => {
            observer?.disconnect();
            instance.destroy();
            cy.current = null;
        };
    }, [graph]);

    useEffect(() => {
        const instance = cy.current;
        if (!instance) return;
        instance.edges().unselect();
        if (selectedId) instance.getElementById(selectedId).select();
    }, [selectedId, graph]);

    return <div ref={container} role="img" aria-label={label} className={styles.canvas} />;
}
