import { DEFAULT_ROOT, isValidRoot } from './root';

/** The analysis root a project was last scanned with, per browser (D-362a): the code lines are read below it. */
const key = (projectId: string) => `quancrypt.scanRoot:${projectId}`;

export function loadRoot(projectId: string): string {
    try {
        const value = window.localStorage.getItem(key(projectId));
        return value !== null && isValidRoot(value) ? value : DEFAULT_ROOT;
    } catch {
        return DEFAULT_ROOT;
    }
}

export function saveRoot(projectId: string, root: string): void {
    try {
        window.localStorage.setItem(key(projectId), root);
    } catch {
        // Without storage the default root is used next time.
    }
}
