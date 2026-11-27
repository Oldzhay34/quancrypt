import { ChatReasoning } from '@/components/ui/chat-reasoning';
import type { ReasoningStep } from '@/components/ui/chat-reasoning';
import type { StepEvent } from '@/shared/api/types';
import { useI18n } from '@/shared/i18n';
import type { MessageKey } from '@/shared/i18n';

const STEP_KEYS = {
    INPUT_GUARD: 'chat.step.INPUT_GUARD',
    ROUTE: 'chat.step.ROUTE',
    GATHER_CONTEXT: 'chat.step.GATHER_CONTEXT',
    PLAN: 'chat.step.PLAN',
    ACT: 'chat.step.ACT',
    VERIFY: 'chat.step.VERIFY',
    REPORT: 'chat.step.REPORT',
    ANSWER: 'chat.step.ANSWER',
    OUTPUT_GUARD: 'chat.step.OUTPUT_GUARD',
} as const satisfies Record<StepEvent['step'], MessageKey>;

const AGENT_KEYS = {
    SUPERVISOR: 'chat.agent.SUPERVISOR',
    DISCOVERY: 'chat.agent.DISCOVERY',
    TOPOLOGY: 'chat.agent.TOPOLOGY',
    PLANNER: 'chat.agent.PLANNER',
} as const satisfies Record<NonNullable<StepEvent['agent']>, MessageKey>;

const STATUS_KEYS = {
    FAILED: 'chat.stepStatus.FAILED',
    STOPPED: 'chat.stepStatus.STOPPED',
    BUDGET_EXCEEDED: 'chat.stepStatus.BUDGET_EXCEEDED',
} as const satisfies Record<Exclude<StepEvent['status'], 'SUCCEEDED'>, MessageKey>;

/** The steps of the last answer: what ran and which tools it used, never model text (D-350f). */
export function ReasoningSteps({ steps, running }: { steps: StepEvent[]; running: boolean }) {
    const { t } = useI18n();
    if (steps.length === 0) return null;
    const rows: ReasoningStep[] = steps.map((step, index) => ({
        id: `${index}-${step.step}`,
        label: step.agent
            ? `${t(AGENT_KEYS[step.agent])}: ${t(STEP_KEYS[step.step])}`
            : t(STEP_KEYS[step.step]),
        status: step.status === 'SUCCEEDED' ? undefined : t(STATUS_KEYS[step.status]),
        detail: step.tools.join(', '),
    }));
    const failed = steps.filter((step) => step.status !== 'SUCCEEDED').length;
    return (
        <ChatReasoning
            className="mt-2"
            steps={rows}
            running={running}
            title={
                running
                    ? t('chat.steps.running')
                    : failed > 0
                      ? t('chat.steps.failed', { count: String(rows.length), failed: String(failed) })
                      : t('chat.steps.done', { count: String(rows.length) })
            }
        />
    );
}
