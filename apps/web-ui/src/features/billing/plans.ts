export type PlanId = 'free' | 'plus' | 'pro';

export interface Plan {
    id: PlanId;
    name: string;
    /** US dollars to pay, and the crossed-out list price (D-357b). */
    price: number;
    listPrice: number;
    /** Tokens a week; chosen values, not measured, and not enforced (D-358a). */
    weeklyTokens: number;
    popular: boolean;
}

export const PLANS: readonly Plan[] = [
    { id: 'free', name: 'Free', price: 0, listPrice: 0, weeklyTokens: 50_000, popular: false },
    { id: 'plus', name: 'Plus', price: 10, listPrice: 20, weeklyTokens: 500_000, popular: true },
    { id: 'pro', name: 'Pro', price: 25, listPrice: 50, weeklyTokens: 2_000_000, popular: false },
];

export const planById = (id: string | null): Plan =>
    PLANS.find((plan) => plan.id === id) ?? (PLANS[0] as Plan);
