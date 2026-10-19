/** The session token (guardrails-security section 6): read from the URL fragment, kept in memory and sessionStorage, then removed from the address bar. */

const STORAGE_KEY = 'quancrypt.session';
/** `quancrypt init` makes 32 random bytes, base64url without padding: 43 characters. */
const TOKEN_PATTERN = /^[A-Za-z0-9_-]{43}$/;

export function isValidToken(value: string | null | undefined): value is string {
    return typeof value === 'string' && TOKEN_PATTERN.test(value);
}

/** The token also lives in module memory, so a browser that blocks sessionStorage still works for this page. */
let memoryToken: string | null = null;

function readStored(win: Window): string | null {
    try {
        const value = win.sessionStorage.getItem(STORAGE_KEY);
        return isValidToken(value) ? value : null;
    } catch {
        return null;
    }
}

function store(win: Window, token: string): void {
    try {
        win.sessionStorage.setItem(STORAGE_KEY, token);
    } catch {
        // Storage may be blocked; the token then lives in memory only.
    }
}

export function clearStoredToken(win: Window = window): void {
    memoryToken = null;
    try {
        win.sessionStorage.removeItem(STORAGE_KEY);
    } catch {
        // Nothing to clear.
    }
}

/**
 * Takes the token from `#token=...` when there is one (and removes the fragment from the address bar at once),
 * otherwise from sessionStorage. An invalid fragment value is discarded, never kept.
 */
export function acquireToken(win: Window = window): string | null {
    const fragment = win.location.hash.startsWith('#') ? win.location.hash.slice(1) : win.location.hash;
    const params = new URLSearchParams(fragment);
    if (params.has('token')) {
        const candidate = params.get('token');
        win.history.replaceState(win.history.state, '', win.location.pathname + win.location.search);
        if (isValidToken(candidate)) {
            memoryToken = candidate;
            store(win, candidate);
            return candidate;
        }
        return null;
    }
    return memoryToken ?? readStored(win);
}
