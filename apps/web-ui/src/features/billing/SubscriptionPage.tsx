import { motion } from 'framer-motion';
import { Check, Star } from 'lucide-react';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useI18n } from '@/shared/i18n';
import { Page } from '@/shared/ui';
import { celebrate } from './celebrate';
import { loadPlan, savePlan } from './planStore';
import { PLANS } from './plans';
import type { Plan, PlanId } from './plans';

/**
 * The three plans (adapted from the given pricing component, D-358): a demo. Nothing is bought, no payment detail is
 * asked for, and the choice only changes what the usage screen measures against.
 */
export function SubscriptionPage() {
    const { t, language } = useI18n();
    const [selected, setSelected] = useState<PlanId>(loadPlan);
    const money = new Intl.NumberFormat(language, {
        style: 'currency',
        currency: 'USD',
        maximumFractionDigits: 0,
    });
    const number = new Intl.NumberFormat(language);

    const choose = (plan: Plan) => {
        savePlan(plan.id);
        setSelected(plan.id);
        celebrate();
    };

    return (
        <Page title={t('menu.subscription')} wide>
            <p className="m-0 mb-2 max-w-xl text-muted-foreground">{t('subscription.intro')}</p>
            <p
                role="note"
                className="m-0 mb-6 inline-block rounded-full border border-border bg-card px-4 py-1 text-sm"
            >
                {t('subscription.demo')}
            </p>
            <ul className="m-0 grid max-w-5xl list-none grid-cols-1 items-stretch gap-4 p-0 py-4 [perspective:1200px] md:grid-cols-3">
                {PLANS.map((plan, index) => (
                    <motion.li
                        key={plan.id}
                        initial={{ y: 40, opacity: 0 }}
                        animate={{
                            y: plan.popular ? -12 : 0,
                            opacity: 1,
                            rotateY: plan.popular ? 0 : index === 0 ? 6 : -6,
                        }}
                        transition={{ type: 'spring', stiffness: 100, damping: 20, delay: index * 0.1 }}
                        className={cn(
                            'relative flex flex-col rounded-2xl border bg-card p-6 text-center max-md:!transform-none',
                            plan.popular ? 'z-10 border-2 border-highlight' : 'border-border',
                        )}
                    >
                        {plan.popular ? (
                            <span className="absolute top-0 right-0 flex items-center gap-1 rounded-tr-xl rounded-bl-xl bg-highlight px-3 py-1 text-xs font-semibold text-highlight-foreground">
                                <Star aria-hidden="true" className="h-3.5 w-3.5 fill-current" />
                                {t('subscription.popular')}
                            </span>
                        ) : null}
                        <h2 className="m-0 text-base font-semibold text-muted-foreground">{plan.name}</h2>
                        <p className="mt-5 mb-0 flex items-baseline justify-center gap-3">
                            {plan.listPrice > plan.price ? (
                                <del className="text-xl text-muted-foreground">
                                    <span className="sr-only">{t('subscription.listPrice')} </span>
                                    {money.format(plan.listPrice)}
                                </del>
                            ) : null}
                            <span className="text-5xl font-bold tracking-tight">
                                {money.format(plan.price)}
                            </span>
                            <span className="text-sm text-muted-foreground">
                                {t('subscription.perMonth')}
                            </span>
                        </p>
                        <p className="m-0 mt-1 min-h-6 text-sm font-semibold">
                            {plan.listPrice > plan.price ? t('subscription.discount') : ''}
                        </p>
                        <ul className="mt-4 mb-6 flex list-none flex-col gap-2 p-0 text-left text-sm">
                            {[
                                t('subscription.tokens', { count: number.format(plan.weeklyTokens) }),
                                t('subscription.allFeatures'),
                            ].map((feature) => (
                                <li key={feature} className="flex items-start gap-2">
                                    <Check
                                        aria-hidden="true"
                                        className="mt-0.5 h-4 w-4 shrink-0 text-primary"
                                    />
                                    {feature}
                                </li>
                            ))}
                        </ul>
                        <Button
                            variant={plan.popular ? 'default' : 'outline'}
                            className="mt-auto w-full"
                            disabled={selected === plan.id}
                            onClick={() => choose(plan)}
                        >
                            {selected === plan.id
                                ? t('subscription.current')
                                : t('subscription.choose', { plan: plan.name })}
                        </Button>
                    </motion.li>
                ))}
            </ul>
        </Page>
    );
}
