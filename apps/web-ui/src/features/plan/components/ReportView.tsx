import { errorMessageKey } from '@/shared/api';
import { saveFile } from '@/shared/download';
import { useI18n } from '@/shared/i18n';
import { Button, ErrorBanner, Spinner } from '@/shared/ui';
import { usePlanReport } from '../hooks';
import styles from '../Plan.module.css';
import { MarkdownView } from './MarkdownView';

/** The plan report: shown as a document, saved as Markdown, or printed (the browser's print dialog saves it as PDF, D-15). */
export function ReportView({ scanId }: { scanId: string }) {
    const { t, language } = useI18n();
    const report = usePlanReport(scanId);
    if (report.isPending) return <Spinner label={t('common.loading')} />;
    if (report.isError) return <ErrorBanner>{t(errorMessageKey(report.error))}</ErrorBanner>;
    const markdown = report.data;
    if (markdown === null) return <p>{t('plan.none')}</p>;
    return (
        <>
            <div className={`${styles.reportActions} ${styles.noPrint}`}>
                <Button
                    onClick={() =>
                        saveFile(
                            new Blob([markdown], { type: 'text/markdown;charset=utf-8' }),
                            `quancrypt-plan-${scanId.slice(0, 8)}-${language}.md`,
                        )
                    }
                >
                    {t('plan.report.download')}
                </Button>
                <Button variant="primary" onClick={() => window.print()}>
                    {t('plan.report.print')}
                </Button>
            </div>
            <MarkdownView source={markdown} />
        </>
    );
}
