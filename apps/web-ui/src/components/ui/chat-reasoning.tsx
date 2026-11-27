import { CircleAlert } from 'lucide-react';
import { useState } from 'react';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { cn } from '@/lib/utils';

export interface ReasoningStep {
    id: string;
    label: string;
    detail?: string;
    /** Set (in words) when the step did not succeed: shown with an icon, never by colour alone. */
    status?: string;
}

/**
 * The steps of a running or just finished answer as a collapsible timeline (adapted from the given chat-reasoning
 * component, without the `ai` package, D-350d). It opens while the answer runs and closes when it ends; the user can
 * toggle it either way.
 */
export function ChatReasoning({
    steps,
    running,
    title,
    className,
}: {
    steps: ReasoningStep[];
    running: boolean;
    title: string;
    className?: string;
}) {
    const [toggled, setToggled] = useState<{ running: boolean; value: string } | null>(null);
    // A user choice holds until the answer changes from running to finished or back.
    const value = toggled && toggled.running === running ? toggled.value : running ? 'steps' : '';
    return (
        <Accordion
            type="single"
            collapsible
            value={value}
            onValueChange={(next) => setToggled({ running, value: next })}
            className={cn('w-full', className)}
        >
            <AccordionItem value="steps">
                <AccordionTrigger>{title}</AccordionTrigger>
                <AccordionContent>
                    <ol className="m-0 list-none p-0">
                        {steps.map((step, index) => (
                            <li key={step.id} className="flex gap-2 pl-1">
                                <div aria-hidden="true" className="flex flex-col items-center gap-1 pt-2">
                                    <span
                                        className={cn(
                                            'h-2 w-2 rounded-full',
                                            step.status ? 'bg-destructive' : 'bg-muted-foreground',
                                        )}
                                    />
                                    {index < steps.length - 1 ? (
                                        <span className="w-0.5 flex-1 rounded-full bg-border" />
                                    ) : null}
                                </div>
                                <div className="flex-1 py-1 text-muted-foreground">
                                    <span className={cn(step.status && 'text-destructive')}>
                                        {step.label}
                                    </span>
                                    {step.status ? (
                                        <span className="ml-2 inline-flex items-center gap-1 text-destructive">
                                            <CircleAlert aria-hidden="true" className="h-3.5 w-3.5" />
                                            {step.status}
                                        </span>
                                    ) : null}
                                    {step.detail ? (
                                        <code className="ml-2 text-xs break-all">{step.detail}</code>
                                    ) : null}
                                </div>
                            </li>
                        ))}
                    </ol>
                </AccordionContent>
            </AccordionItem>
        </Accordion>
    );
}
