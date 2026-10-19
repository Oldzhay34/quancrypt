import { Outlet } from 'react-router';
import { Header } from './Header';
import { SideNav } from './SideNav';
import styles from './Layout.module.css';

export function AppShell() {
    return (
        <div className={styles.shell}>
            <Header />
            <div className={styles.body}>
                <SideNav />
                <main className={styles.main}>
                    <Outlet />
                </main>
            </div>
        </div>
    );
}
