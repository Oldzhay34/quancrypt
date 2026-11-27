import { ArrowUp, Cpu, ListChecks, Square } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import type { FormEvent, KeyboardEvent } from 'react';
import { Link } from 'react-router';
import { Button } from '@/components/ui/button';
import { useI18n } from '@/shared/i18n';
import { MAX_MESSAGE_CHARS } from '../limits';
import { LOCAL_CHAT_MODEL } from '../model';

interface ComposerProps {
    /** This chat's answer is running: typing stays possible and Stop takes the place of Send (D-356d). */
    busy: boolean;
    /** As many answers run as allowed (D-351): sending waits. */
    blocked: boolean;
    canStop: boolean;
    stopping: boolean;
    onStop: () => void;
    onSend: (text: string) => void;
}

const MAX_HEIGHT = 200;

/** The message box: Enter sends, Shift+Enter adds a line, and Enter during IME composition is left to the IME. */
export function Composer({ busy, blocked, canStop, stopping, onStop, onSend }: ComposerProps) {
    const { t } = useI18n();
    const [value, setValue] = useState('');
    const fieldId = useId();
    const hintId = useId();
    const field = useRef<HTMLTextAreaElement>(null);

    useEffect(() => {
        const area = field.current;
        if (!area) return;
        area.style.height = 'auto';
        area.style.height = `${Math.min(area.scrollHeight, MAX_HEIGHT)}px`;
    }, [value]);

    const submit = () => {
        const text = value.trim();
        if (text === '' || busy || blocked) return;
        onSend(text);
        setValue('');
    };
    const onSubmit = (event: FormEvent) => {
        event.preventDefault();
        submit();
    };
    const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
        if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return;
        event.preventDefault();
        submit();
    };

    return (
        <form className="w-full" onSubmit={onSubmit}>
            <label htmlFor={fieldId} className="sr-only">
                {t('chat.composer.label')}
            </label>
            <div className="rounded-3xl border border-border bg-card shadow-lg focus-within:border-ring">
                <textarea
                    id={fieldId}
                    ref={field}
                    rows={1}
                    value={value}
                    maxLength={MAX_MESSAGE_CHARS}
                    placeholder={t('chat.composer.placeholder')}
                    aria-describedby={hintId}
                    onChange={(event) => setValue(event.target.value)}
                    onKeyDown={onKeyDown}
                    className="block w-full resize-none rounded-t-3xl border-0 bg-transparent px-5 pt-4 pb-2 font-[inherit] text-[15px] text-foreground placeholder:text-muted-foreground focus:outline-none"
                />
                <div className="flex flex-wrap items-center gap-2 px-3 pb-3">
                    <span className="inline-flex items-center gap-1.5 px-2 text-xs text-muted-foreground">
                        <Cpu aria-hidden="true" className="h-3.5 w-3.5" />
                        {t('chat.composer.model', { model: LOCAL_CHAT_MODEL })}
                    </span>
                    <span className="flex-1" />
                    <Button asChild variant="ghost" size="sm">
                        <Link to="/plan" className="no-underline">
                            <ListChecks aria-hidden="true" className="h-4 w-4" />
                            {t('nav.plan')}
                        </Link>
                    </Button>
                    {busy ? (
                        <Button
                            size="icon"
                            className="rounded-full"
                            aria-label={stopping ? t('header.stopping') : t('header.stop')}
                            title={stopping ? t('header.stopping') : t('header.stop')}
                            disabled={!canStop || stopping}
                            onClick={onStop}
                        >
                            <Square aria-hidden="true" className="h-3.5 w-3.5 fill-current" />
                        </Button>
                    ) : (
                        <Button
                            type="submit"
                            size="icon"
                            className="rounded-full"
                            aria-label={t('chat.composer.send')}
                            title={t('chat.composer.send')}
                            disabled={blocked || value.trim() === ''}
                        >
                            <ArrowUp aria-hidden="true" className="h-4 w-4" />
                        </Button>
                    )}
                </div>
            </div>
            <p id={hintId} className="mt-1.5 mb-0 text-center text-xs text-muted-foreground">
                {t('chat.composer.hint')}
            </p>
        </form>
    );
}
