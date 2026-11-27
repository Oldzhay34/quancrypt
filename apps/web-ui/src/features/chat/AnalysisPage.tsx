import { Square } from 'lucide-react';
import { useI18n } from '@/shared/i18n';
import { useProject } from '@/shared/project';
import { Button, ErrorBanner, Page } from '@/shared/ui';
import { InitialScanPanel } from './components/InitialScanPanel';
import { MessageBubble } from './components/MessageBubble';
import { ReasoningSteps } from './components/ReasoningSteps';
import { useLatestScan, useScanController } from './hooks';
import { MAX_PARALLEL } from './runs';

/** The project analysis (UC1) on its own screen (D-356c): start a scan, follow its steps, read the summary. */
export function AnalysisPage() {
    const { project } = useProject();
    if (!project) return null;
    return <Analysis key={project.id} projectId={project.id} />;
}

function Analysis({ projectId }: { projectId: string }) {
    const { t } = useI18n();
    const latestScan = useLatestScan(projectId);
    const scan = useScanController(projectId);
    const turn = scan.state.turn;
    const hasAnswer = turn !== null && (turn.text !== '' || turn.evidence.length > 0);

    return (
        <Page title={t('nav.analysis')}>
            <InitialScanPanel
                overview={latestScan.data}
                loadError={latestScan.error}
                busy={scan.busy || scan.blocked}
                scanning={scan.busy}
                onStart={scan.start}
            />
            {scan.blocked ? (
                <p role="status" className="m-0 mb-3 text-sm text-muted-foreground">
                    {t('chat.parallel.limit', { count: String(MAX_PARALLEL) })}
                </p>
            ) : null}
            {scan.busy ? (
                <Button disabled={!scan.canStop || scan.stopping} onClick={scan.stop}>
                    <Square aria-hidden="true" className="mr-1 inline h-3.5 w-3.5" />
                    {scan.stopping ? t('header.stopping') : t('header.stop')}
                </Button>
            ) : null}
            <ReasoningSteps steps={scan.state.steps} running={turn?.status === 'streaming'} />
            <div aria-live="polite">
                {hasAnswer ? <MessageBubble author="scan" text={turn.text} evidence={turn.evidence} /> : null}
            </div>
            {turn?.failureKey ? (
                turn.status === 'stopped' ? (
                    <p role="status">{t(turn.failureKey)}</p>
                ) : (
                    <ErrorBanner>{t(turn.failureKey)}</ErrorBanner>
                )
            ) : null}
        </Page>
    );
}
