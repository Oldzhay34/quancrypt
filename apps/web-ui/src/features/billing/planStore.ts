import { planById } from './plans';
import type { PlanId } from './plans';

/** The chosen demo plan: a per-browser convenience, nothing is bought and nothing is enforced (D-358a). */
const KEY = 'quancrypt.plan';

export function loadPlan(): PlanId {
    try {
        return planById(window.localStorage.getItem(KEY)).id;
    } catch {
        return 'free';
    }
}

export function savePlan(id: PlanId): void {
    try {
        window.localStorage.setItem(KEY, id);
    } catch {
        // Without storage the choice lasts as long as the screen.
    }
}
