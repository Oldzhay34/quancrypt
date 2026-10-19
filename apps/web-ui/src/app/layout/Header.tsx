import { useI18n } from '@/shared/i18n';
import type { Language } from '@/shared/i18n';
import { useProject } from '@/shared/project';
import { useActiveSession } from '@/shared/session';
import { Button } from '@/shared/ui';
import styles from './Layout.module.css';

export function Header() {
    const { t, language, setLanguage } = useI18n();
    const { project, projects, selectProject } = useProject();
    const { sessionId, stop, stopping } = useActiveSession();

    return (
        <header className={styles.header}>
            <strong className={styles.brand}>{t('app.title')}</strong>
            <div className={styles.project}>
                {projects.length > 1 ? (
                    <select
                        aria-label={t('header.project')}
                        value={project?.id}
                        onChange={(event) => selectProject(event.target.value)}
                    >
                        {projects.map((item) => (
                            <option key={item.id} value={item.id}>
                                {item.displayName}
                            </option>
                        ))}
                    </select>
                ) : (
                    <span title={t('header.project')}>{project?.displayName}</span>
                )}
            </div>
            <select
                aria-label={t('lang.label')}
                value={language}
                onChange={(event) => setLanguage(event.target.value as Language)}
            >
                <option value="tr">Türkçe</option>
                <option value="en">English</option>
            </select>
            <Button variant="danger" disabled={!sessionId || stopping} onClick={stop}>
                {stopping ? t('header.stopping') : t('header.stop')}
            </Button>
        </header>
    );
}
