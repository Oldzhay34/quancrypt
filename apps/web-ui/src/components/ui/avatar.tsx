import * as AvatarPrimitive from '@radix-ui/react-avatar';
import type { ComponentProps } from 'react';
import { cn } from '@/lib/utils';

export function Avatar({ className, ...props }: ComponentProps<typeof AvatarPrimitive.Root>) {
    return (
        <AvatarPrimitive.Root
            className={cn('relative flex h-8 w-8 shrink-0 overflow-hidden rounded-full', className)}
            {...props}
        />
    );
}

/** Only a local initial or icon is shown: no image is ever loaded (D-348b). */
export function AvatarFallback({ className, ...props }: ComponentProps<typeof AvatarPrimitive.Fallback>) {
    return (
        <AvatarPrimitive.Fallback
            className={cn(
                'flex h-full w-full items-center justify-center rounded-full bg-muted text-xs font-semibold',
                className,
            )}
            {...props}
        />
    );
}
