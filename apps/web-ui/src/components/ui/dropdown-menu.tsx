import * as Menu from '@radix-ui/react-dropdown-menu';
import { Check } from 'lucide-react';
import type { ComponentProps } from 'react';
import { cn } from '@/lib/utils';

/*
 * The shadcn dropdown menu, written by hand (D-350d). It is not modal: the modal variant locks scrolling by adding a
 * <style> element, which the page's `style-src 'self'` policy refuses.
 */
export function DropdownMenu(props: ComponentProps<typeof Menu.Root>) {
    return <Menu.Root modal={false} {...props} />;
}

export const DropdownMenuTrigger = Menu.Trigger;

export function DropdownMenuContent({ className, ...props }: ComponentProps<typeof Menu.Content>) {
    return (
        <Menu.Portal>
            <Menu.Content
                sideOffset={6}
                className={cn(
                    'z-20 min-w-52 rounded-xl border border-border bg-card p-1 text-foreground shadow-xl',
                    className,
                )}
                {...props}
            />
        </Menu.Portal>
    );
}

export function DropdownMenuItem({ className, ...props }: ComponentProps<typeof Menu.Item>) {
    return (
        <Menu.Item
            className={cn(
                'flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm text-foreground no-underline outline-none data-[highlighted]:bg-accent',
                className,
            )}
            {...props}
        />
    );
}

export const DropdownMenuRadioGroup = Menu.RadioGroup;

export function DropdownMenuLabel({ className, ...props }: ComponentProps<typeof Menu.Label>) {
    return (
        <Menu.Label
            className={cn('border-t border-border px-3 pt-2 pb-1 text-xs text-muted-foreground', className)}
            {...props}
        />
    );
}

export function DropdownMenuRadioItem({ children, ...props }: ComponentProps<typeof Menu.RadioItem>) {
    return (
        <Menu.RadioItem
            className="flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm text-foreground outline-none data-[highlighted]:bg-accent"
            {...props}
        >
            <span className="flex h-4 w-4 items-center justify-center">
                <Menu.ItemIndicator>
                    <Check aria-hidden="true" className="h-4 w-4" />
                </Menu.ItemIndicator>
            </span>
            {children}
        </Menu.RadioItem>
    );
}
