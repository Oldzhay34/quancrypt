import { useI18n } from '@/shared/i18n';
import { useProject } from '@/shared/project';
import { SUPERSET_URL, useSupersetReachable } from '@/shared/superset';
import styles from './Layout.module.css';

export function Header() {
    const { t } = useI18n();
    const { project, projects, selectProject } = useProject();
    const dashboardUp = useSupersetReachable();

    return (
        <header className={styles.header}>
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
            {dashboardUp ? (
                <a href={SUPERSET_URL} target="_blank" rel="noopener noreferrer" className={styles.dashboard}>
                    {t('header.dashboard')}
                </a>
            ) : null}
        </header>
    );
}
