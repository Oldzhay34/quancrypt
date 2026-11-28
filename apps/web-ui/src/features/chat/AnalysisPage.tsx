import { Square } from 'lucide-react';
import { useState } from 'react';
import { useI18n } from '@/shared/i18n';
import { useProject } from '@/shared/project';
import { Button, ErrorBanner, Page } from '@/shared/ui';
import { FindingList } from './components/FindingList';
import { InitialScanPanel } from './components/InitialScanPanel';
import { MessageBubble } from './components/MessageBubble';
import { ReasoningSteps } from './components/ReasoningSteps';
import { Reveal } from './components/Reveal';
import { ScanSummaryCard } from './components/ScanSummaryCard';
import { useLatestScan, useScanController } from './hooks';
import { loadRoot, saveRoot } from './rootStore';
import { MAX_PARALLEL } from './runs';

/** The project analysis (UC1) on its own screen (D-356c): start a scan, follow its steps, read what was found. */
export function AnalysisPage() {
    const { project } = useProject();
    if (!project) return null;
    return <Analysis key={project.id} projectId={project.id} />;
}

function Analysis({ projectId }: { projectId: string }) {
    const { t } = useI18n();
    const latestScan = useLatestScan(projectId);
    const scan = useScanController(projectId);
    const [codeRoot, setCodeRoot] = useState(() => loadRoot(projectId));
    const turn = scan.state.turn;
    const hasAnswer = turn !== null && (turn.text !== '' || turn.evidence.length > 0);
    const overview = latestScan.data;

    const rememberRoot = (root: string) => {
        saveRoot(projectId, root);
        setCodeRoot(root);
    };
    const start = (root: string) => {
        rememberRoot(root);
        scan.start(root);
    };

    return (
        <Page title={t('nav.analysis')} wide>
            <div className="flex max-w-5xl flex-col gap-4">
                <Reveal order={0}>
                    <InitialScanPanel
                        overview={overview}
                        loadError={latestScan.error}
                        busy={scan.busy || scan.blocked}
                        scanning={scan.busy}
                        onStart={start}
                        initialRoot={codeRoot}
                        onShowCode={rememberRoot}
                    />
                </Reveal>
                {scan.blocked ? (
                    <p role="status" className="m-0 text-sm text-muted-foreground">
                        {t('chat.parallel.limit', { count: String(MAX_PARALLEL) })}
                    </p>
                ) : null}
                {scan.busy ? (
                    <div>
                        <Button disabled={!scan.canStop || scan.stopping} onClick={scan.stop}>
                            <Square aria-hidden="true" className="mr-1 inline h-3.5 w-3.5" />
                            {scan.stopping ? t('header.stopping') : t('header.stop')}
                        </Button>
                    </div>
                ) : null}
                <ReasoningSteps steps={scan.state.steps} running={turn?.status === 'streaming'} />
                <div aria-live="polite">
                    {hasAnswer ? (
                        <MessageBubble author="scan" text={turn.text} evidence={turn.evidence} />
                    ) : null}
                </div>
                {turn?.failureKey ? (
                    turn.status === 'stopped' ? (
                        <p role="status">{t(turn.failureKey)}</p>
                    ) : (
                        <ErrorBanner>{t(turn.failureKey)}</ErrorBanner>
                    )
                ) : null}
                {overview ? (
                    <>
                        <Reveal order={1}>
                            <ScanSummaryCard overview={overview} />
                        </Reveal>
                        <Reveal order={2}>
                            <FindingList
                                key={overview.summary.scan.id}
                                scanId={overview.summary.scan.id}
                                root={codeRoot}
                            />
                        </Reveal>
                    </>
                ) : null}
            </div>
        </Page>
    );
}
