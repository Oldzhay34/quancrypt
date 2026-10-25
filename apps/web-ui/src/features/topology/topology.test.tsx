import { act, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { renderApp } from '@/test/renderApp';
import { reviewBackend } from '@/test/review';

interface FakeCy {
    config: { elements: { data: Record<string, unknown> }[]; style: unknown[] };
    handlers: { event: string; selector: string | null; handler: (event: unknown) => void }[];
    destroy: ReturnType<typeof vi.fn>;
    selected: string[];
    resize: ReturnType<typeof vi.fn>;
    fit: ReturnType<typeof vi.fn>;
}

// Cytoscape draws on a canvas, which jsdom does not have: a stand-in records how the graph is built and lets the test tap it.
const { instances } = vi.hoisted(() => ({ instances: [] as FakeCy[] }));

vi.mock('cytoscape', () => ({
    default: (config: FakeCy['config']) => {
        const cy: FakeCy & Record<string, unknown> = {
            config,
            handlers: [],
            destroy: vi.fn(),
            selected: [],
            resize: vi.fn(),
            fit: vi.fn(),
            on(
                event: string,
                selectorOrHandler: string | ((e: unknown) => void),
                handler?: (e: unknown) => void,
            ) {
                cy.handlers.push(
                    typeof selectorOrHandler === 'string'
                        ? { event, selector: selectorOrHandler, handler: handler as (e: unknown) => void }
                        : { event, selector: null, handler: selectorOrHandler },
                );
            },
            edges: () => ({ unselect: () => (cy.selected = []) }),
            getElementById: (id: string) => ({ select: () => cy.selected.push(id) }),
        };
        instances.push(cy);
        return cy;
    },
}));

const tap = (cy: FakeCy, selector: string | null, target: unknown) =>
    act(() => {
        for (const entry of cy.handlers) {
            if (entry.event === 'tap' && entry.selector === selector) entry.handler({ target });
        }
    });

describe('topology screen', () => {
    it('builds the graph from the recorded topology: node kinds, edge status colours, and a legend', async () => {
        instances.length = 0;
        renderApp(reviewBackend(), { path: '/topology' });

        await screen.findByRole('img', { name: /Servis topolojisi grafiği/ });
        const cy = instances.at(-1) as FakeCy;
        const nodes = cy.config.elements.filter((element) => element.data.kind !== undefined);
        const edges = cy.config.elements.filter((element) => element.data.status !== undefined);
        expect(nodes.map((node) => node.data.kind)).toEqual(['GATEWAY', 'SERVICE', 'BROKER', 'DEVICE']);
        expect(edges.map((edge) => edge.data.status)).toEqual(['VULNERABLE', 'RESISTANT', 'UNKNOWN']);
        const styles = JSON.stringify(cy.config.style);
        expect(styles).toContain('#D55E00');
        expect(styles).toContain('#0072B2');
        expect(styles).toContain('round-rectangle');
        expect(styles).toContain('hexagon');

        const legend = screen.getByRole('region', { name: 'Lejant' });
        expect(within(legend).getByText('Kuantuma açık (VULNERABLE)')).toBeInTheDocument();
        expect(within(legend).getByText('Kuantuma dirençli (RESISTANT)')).toBeInTheDocument();
        expect(within(legend).getByText(/Saha cihazı: fıçı/)).toBeInTheDocument();
    });

    it('opens the side panel when a connection is tapped, with protocol, TLS, mTLS, status and findings', async () => {
        instances.length = 0;
        renderApp(reviewBackend(), { path: '/topology' });
        await screen.findByRole('img');
        const cy = instances.at(-1) as FakeCy;

        await tap(cy, 'edge', { id: () => 'e:0' });

        const panel = await screen.findByRole('complementary', { name: 'Bağlantı ayrıntısı' });
        expect(within(panel).getByText('qbank-gateway → qbank-payment-service')).toBeInTheDocument();
        const facts = within(panel)
            .getAllByRole('definition')
            .map((item) => item.textContent);
        expect(facts).toEqual(['HTTP', 'Evet', 'Evet', 'Kuantuma açık (VULNERABLE)', 'Kayıtlı değil', '1']);
        expect(within(panel).getByText('src/main/java/Pay1.java:11')).toBeInTheDocument();
        expect(within(panel).getByText('RSA · TLS_KEY_EXCHANGE · P1')).toBeInTheDocument();
        expect(within(panel).getByText('src/main/java/Pay2.java')).toBeInTheDocument();
        expect(cy.selected).toEqual(['e:0']);
    });

    it('tells apart a connection without findings and clears the panel when empty space is tapped', async () => {
        instances.length = 0;
        renderApp(reviewBackend(), { path: '/topology' });
        await screen.findByRole('img');
        const cy = instances.at(-1) as FakeCy;

        await tap(cy, 'edge', { id: () => 'e:2' });
        const panel = await screen.findByRole('complementary');
        expect(within(panel).getByText('Bu bağlantıya bağlı bulgu yok.')).toBeInTheDocument();
        expect(within(panel).getByText('Bilinmiyor')).toBeInTheDocument();

        await tap(cy, null, cy);
        expect(screen.queryByRole('complementary')).toBeNull();
    });

    it('lets the keyboard do the same through the connection table, and closes with the button', async () => {
        instances.length = 0;
        const user = userEvent.setup();
        renderApp(reviewBackend(), { path: '/topology' });

        const table = await screen.findByRole('table', { name: 'Bağlantılar' });
        expect(within(table).getAllByRole('row')).toHaveLength(4);
        expect(within(table).getByText('Kuantuma dirençli (RESISTANT)')).toBeInTheDocument();

        await user.click(within(table).getByRole('button', { name: 'terminal-001 → mosquitto' }));
        const panel = await screen.findByRole('complementary');
        expect(within(panel).getByText('ML_KEM · KEY_AGREEMENT · P2')).toBeInTheDocument();
        expect(within(panel).getByText('MQTT')).toBeInTheDocument();
        await user.click(within(panel).getByRole('button', { name: 'Kapat' }));
        expect(screen.queryByRole('complementary')).toBeNull();
    });

    it('fits the graph again when its container changes size, for instance when the side panel opens', async () => {
        instances.length = 0;
        const observers: { callback: () => void; disconnected: boolean }[] = [];
        vi.stubGlobal(
            'ResizeObserver',
            class {
                private readonly entry: { callback: () => void; disconnected: boolean };
                constructor(callback: () => void) {
                    this.entry = { callback, disconnected: false };
                    observers.push(this.entry);
                }
                observe() {}
                disconnect() {
                    this.entry.disconnected = true;
                }
            },
        );
        const { unmount } = renderApp(reviewBackend(), { path: '/topology' });
        await screen.findByRole('img');
        const cy = instances.at(-1) as FakeCy;

        act(() => observers.at(-1)?.callback());

        expect(cy.resize).toHaveBeenCalled();
        expect(cy.fit).toHaveBeenCalled();
        unmount();
        expect(observers.at(-1)?.disconnected).toBe(true);
        vi.unstubAllGlobals();
    });

    it('destroys the graph when the screen is left', async () => {
        instances.length = 0;
        const { unmount } = renderApp(reviewBackend(), { path: '/topology' });
        await screen.findByRole('img');
        const cy = instances.at(-1) as FakeCy;

        unmount();

        expect(cy.destroy).toHaveBeenCalled();
    });

    it('says so when the scan has no recorded topology', async () => {
        const backend = reviewBackend();
        if (backend.overview) backend.overview.topology = null;
        renderApp(backend, { path: '/topology' });

        expect(await screen.findByText('Bu tarama için topoloji kaydedilmemiş.')).toBeInTheDocument();
        expect(screen.queryByRole('img')).toBeNull();
    });
});
