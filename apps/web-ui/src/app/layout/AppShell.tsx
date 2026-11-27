import { Outlet } from 'react-router';
import { RunNotices } from '@/features/chat';
import { Header } from './Header';
import { SideNav } from './SideNav';
import styles from './Layout.module.css';

export function AppShell() {
    return (
        <div className={styles.shell}>
            <SideNav />
            <div className={styles.column}>
                <Header />
                <main className={styles.main}>
                    <Outlet />
                </main>
            </div>
            <RunNotices />
        </div>
    );
}
