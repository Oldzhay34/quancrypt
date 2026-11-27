import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';
import { errorMessageKey, useApi } from '@/shared/api';
import { useI18n } from '@/shared/i18n';
import { ErrorBanner, Page, Spinner, Tabs } from '@/shared/ui';
import { getUsage } from './api';
import { loadPlan } from './planStore';
import { planById } from './plans';

/** This week's token use against the chosen demo plan (D-358): counted from the service's records, never enforced. */
export function UsagePage() {
    const { t, language } = useI18n();
    const api = useApi();
    const [planId] = useState(loadPlan);
    const plan = planById(planId);
    const usage = useQuery({ queryKey: ['usage'], queryFn: ({ signal }) => getUsage(api, signal) });

    const number = new Intl.NumberFormat(language);
    const used = usage.data ? usage.data.prompt_tokens + usage.data.completion_tokens : 0;
    const percent = Math.round((used / plan.weeklyTokens) * 100);

    return (
        <Page title={t('settings.title')}>
            <Tabs
                label={t('settings.tabs')}
                items={[
                    { to: '/settings', label: t('menu.consents') },
                    { to: '/settings/usage', label: t('menu.usage') },
                ]}
            />
            <h2 className="mt-0">{t('usage.title')}</h2>
            {usage.isError ? <ErrorBanner>{t(errorMessageKey(usage.error))}</ErrorBanner> : null}
            {usage.isPending ? <Spinner label={t('common.loading')} /> : null}
            {usage.data ? (
                <section className="rounded-2xl border border-border bg-card p-5">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <strong>{t('usage.week', { plan: plan.name })}</strong>
                        <span>{t('usage.percent', { percent: number.format(percent) })}</span>
                    </div>
                    <div
                        role="progressbar"
                        aria-label={t('usage.title')}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={Math.min(percent, 100)}
                        className="mt-3 h-3 overflow-hidden rounded-full bg-secondary"
                    >
                        <div
                            className="h-full rounded-full bg-highlight"
                            style={{ width: `${Math.min(percent, 100)}%` }}
                        />
                    </div>
                    <p className="mt-3 mb-0 text-sm">
                        {t('usage.tokens', {
                            used: number.format(used),
                            limit: number.format(plan.weeklyTokens),
                        })}
                    </p>
                    <p className="mt-1 mb-0 text-sm text-muted-foreground">
                        {t('usage.resets', {
                            when: new Date(usage.data.period_end).toLocaleString(language, {
                                dateStyle: 'full',
                                timeStyle: 'short',
                            }),
                        })}
                    </p>
                </section>
            ) : null}
            <p className="text-sm text-muted-foreground">{t('usage.note')}</p>
            <p className="text-sm">
                <Link to="/subscription">{t('usage.changePlan')}</Link>
            </p>
        </Page>
    );
}
