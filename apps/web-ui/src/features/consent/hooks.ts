import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CONSENT_TYPES, useApi } from '@/shared/api';
import type { Consent, ConsentType } from '@/shared/api/types';
import { getConsents, getPrivacyNotice, grantConsent, revokeConsent } from './api';
import { isConsentSeen, markConsentSeen } from './consentSeen';

export function usePrivacyNotice() {
    const api = useApi();
    return useQuery({ queryKey: ['privacy-notice'], queryFn: ({ signal }) => getPrivacyNotice(api, signal) });
}

export function useConsents(projectId: string) {
    const api = useApi();
    return useQuery({
        queryKey: ['consents', projectId],
        queryFn: ({ signal }) => getConsents(api, projectId, signal),
    });
}

/** True while the first-run consent screen must be shown for this project (and the answer is still loading otherwise). */
export function useConsentRequired(projectId: string): {
    loading: boolean;
    error: boolean;
    required: boolean;
} {
    const notice = usePrivacyNotice();
    const consents = useConsents(projectId);
    if (notice.isError || consents.isError) return { loading: false, error: true, required: false };
    if (!notice.data || !consents.data) return { loading: true, error: false, required: false };
    const version = notice.data.version;
    const answered = consents.data.some((consent) => consent.privacyNoticeVersion >= version);
    return { loading: false, error: false, required: !answered && !isConsentSeen(projectId, version) };
}

/** A withdrawn consent is granted again with `If-Match` (its version); a first grant has none. */
function previous(existing: Consent[], type: ConsentType): Consent | undefined {
    return existing.find((consent) => consent.consentType === type);
}

export function useGrantConsents(projectId: string) {
    const api = useApi();
    const client = useQueryClient();
    return useMutation({
        mutationFn: async (input: { types: ConsentType[]; noticeVersion: number; existing: Consent[] }) => {
            for (const type of input.types) {
                const old = previous(input.existing, type);
                await grantConsent(
                    api,
                    projectId,
                    type,
                    input.noticeVersion,
                    old?.revokedAt ? old.version : undefined,
                );
            }
            markConsentSeen(projectId, input.noticeVersion);
        },
        onSettled: () => client.invalidateQueries({ queryKey: ['consents', projectId] }),
    });
}

/**
 * The first-run screen: grants the switches turned on that were not active, withdraws the active ones turned off, and remembers that
 * the screen was shown. An active consent stays as it is, under the notice version it was given with (D-290b).
 */
export function useApplyConsents(projectId: string) {
    const api = useApi();
    const client = useQueryClient();
    return useMutation({
        mutationFn: async (input: {
            selection: Record<ConsentType, boolean>;
            noticeVersion: number;
            existing: Consent[];
        }) => {
            for (const type of CONSENT_TYPES) {
                const old = previous(input.existing, type);
                const active = old !== undefined && old.revokedAt === null;
                if (input.selection[type] && !active) {
                    await grantConsent(
                        api,
                        projectId,
                        type,
                        input.noticeVersion,
                        old?.revokedAt ? old.version : undefined,
                    );
                } else if (!input.selection[type] && old && active) {
                    await revokeConsent(api, projectId, type, old.version);
                }
            }
            markConsentSeen(projectId, input.noticeVersion);
        },
        onSettled: () => client.invalidateQueries({ queryKey: ['consents', projectId] }),
    });
}

export function useRevokeConsent(projectId: string) {
    const api = useApi();
    const client = useQueryClient();
    return useMutation({
        mutationFn: (input: { type: ConsentType; version: number }) =>
            revokeConsent(api, projectId, input.type, input.version),
        onSettled: () => client.invalidateQueries({ queryKey: ['consents', projectId] }),
    });
}
