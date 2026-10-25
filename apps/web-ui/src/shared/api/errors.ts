import { ApiError } from './client';
import type { MessageKey } from '../i18n/tr';

/** The message key to show a user for a failed request. Nothing from the server body is shown. */
export function errorMessageKey(error: unknown): MessageKey {
    if (error instanceof ApiError) {
        if (error.code === 'network') return 'error.network';
        if (error.code === 'session-busy') return 'error.sessionBusy';
        if (error.code === 'upstream-unavailable') return 'error.upstream';
        if (error.code === 'validation-failed') return 'error.validation';
        if (error.code === 'invalid-state-transition') return 'error.invalidTransition';
        if (error.code === 'concurrent-modification') return 'error.concurrent';
        if (error.status === 409 || error.status === 412 || error.status === 428) return 'error.conflict';
    }
    return 'error.generic';
}
