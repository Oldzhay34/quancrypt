/**
 * "The first-run screen was shown" is remembered in this browser only (D-288): core has no such record and the schema does not
 * change. The key names a project and a notice version, so a new notice version asks again.
 */
function key(projectId: string, version: number): string {
    return `consentSeen:${projectId}:${version}`;
}

export function isConsentSeen(projectId: string, version: number): boolean {
    try {
        return window.localStorage.getItem(key(projectId, version)) === '1';
    } catch {
        return false;
    }
}

export function markConsentSeen(projectId: string, version: number): void {
    try {
        window.localStorage.setItem(key(projectId, version), '1');
    } catch {
        // The screen may then be shown again on the next visit.
    }
}
