/**
 * The chat session of a project is remembered in this browser only (D-291c): the service has no "my sessions" endpoint, so
 * without this the history of a closed tab could neither be shown nor deleted. The stored value is a random UUID, not personal
 * data; anything else found under the key is ignored (the value ends up in a URL path).
 */
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function key(projectId: string): string {
    return `chatSession:${projectId}`;
}

export function loadSessionId(projectId: string): string | null {
    try {
        const value = window.localStorage.getItem(key(projectId));
        return value !== null && UUID.test(value) ? value : null;
    } catch {
        return null;
    }
}

export function saveSessionId(projectId: string, sessionId: string): void {
    try {
        window.localStorage.setItem(key(projectId), sessionId);
    } catch {
        // The history then cannot be found again after a reload.
    }
}

export function forgetSessionId(projectId: string): void {
    try {
        window.localStorage.removeItem(key(projectId));
    } catch {
        // Nothing to forget.
    }
}
