import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FakeBackend } from '@/test/fakeBackend';
import { renderApp } from '@/test/renderApp';
import { PLANS } from './plans';

const fire = vi.hoisted(() => vi.fn());
vi.mock('canvas-confetti', () => ({ default: { create: () => fire } }));

describe('usage', () => {
    beforeEach(() => window.localStorage.clear());

    it('shows this week as a percentage of the chosen plan, from the service count', async () => {
        const backend = new FakeBackend();
        renderApp(backend, { path: '/settings/usage' });

        expect(await screen.findByText('%12 kullanıldı')).toBeInTheDocument();
        expect(screen.getByText('6.000 / 50.000 token')).toBeInTheDocument();
        expect(screen.getByRole('progressbar', { name: 'Haftalık kullanım' })).toHaveAttribute(
            'aria-valuenow',
            '12',
        );
        const call = backend.find('GET', '/api/v1/usage')[0];
        expect(call?.url.origin).toBe('http://127.0.0.1:8083');
        expect(call?.headers.get('Authorization')).toMatch(/^Bearer /);
    });

    it('says more than a hundred percent but keeps the bar full: nothing is blocked', async () => {
        const backend = new FakeBackend();
        backend.usage = { ...backend.usage, prompt_tokens: 60_000, completion_tokens: 15_000 };
        renderApp(backend, { path: '/settings/usage' });

        expect(await screen.findByText('%150 kullanıldı')).toBeInTheDocument();
        expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100');
    });

    it('is reached from the settings menu', async () => {
        const user = userEvent.setup();
        renderApp(new FakeBackend(), { path: '/settings' });

        await user.click(await screen.findByRole('button', { name: 'Ayarlar' }));
        const menu = await screen.findByRole('menu');
        expect(
            within(menu)
                .getAllByRole('menuitem')
                .map((item) => item.textContent),
        ).toEqual(['Onaylar', 'Kullanım', 'Abonelik', 'Ayarlar']);
        await user.click(within(menu).getByRole('menuitem', { name: 'Kullanım' }));

        expect(await screen.findByRole('heading', { name: 'Haftalık kullanım' })).toBeInTheDocument();
    });
});

describe('subscription', () => {
    beforeEach(() => {
        window.localStorage.clear();
        fire.mockClear();
    });

    it('keeps the agreed prices and weekly limits', () => {
        expect(PLANS.map((plan) => [plan.name, plan.price, plan.listPrice, plan.weeklyTokens])).toEqual([
            ['Free', 0, 0, 50_000],
            ['Plus', 10, 20, 500_000],
            ['Pro', 25, 50, 2_000_000],
        ]);
    });

    it('says it is a demo, asks for no payment detail, and a chosen plan changes the usage percentage', async () => {
        const backend = new FakeBackend();
        const user = userEvent.setup();
        renderApp(backend, { path: '/subscription' });

        expect(await screen.findByRole('note')).toHaveTextContent('Demo: ödeme alınmaz');
        expect(screen.queryByRole('textbox')).toBeNull();
        expect(screen.getAllByText('/ ay')).toHaveLength(3);
        expect(screen.getByRole('button', { name: 'Seçili plan' })).toBeDisabled();

        await user.click(screen.getByRole('button', { name: 'Plus planını seç' }));

        expect(fire).toHaveBeenCalledOnce();
        expect(window.localStorage.getItem('quancrypt.plan')).toBe('plus');
        // Choosing buys nothing: no request goes out for it.
        expect(backend.calls.filter((call) => call.method !== 'GET')).toHaveLength(0);

        await user.click(screen.getByRole('button', { name: 'Ayarlar' }));
        await user.click(await screen.findByRole('menuitem', { name: 'Kullanım' }));
        await waitFor(() => expect(screen.getByText('6.000 / 500.000 token')).toBeInTheDocument());
        expect(screen.getByText('%1 kullanıldı')).toBeInTheDocument();
    });
});
