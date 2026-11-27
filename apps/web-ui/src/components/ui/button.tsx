import { Slot } from '@radix-ui/react-slot';
import { cva } from 'class-variance-authority';
import type { VariantProps } from 'class-variance-authority';
import type { ButtonHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
    'inline-flex cursor-pointer items-center justify-center gap-2 whitespace-nowrap rounded-full border border-transparent text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-40',
    {
        variants: {
            variant: {
                default: 'bg-primary text-primary-foreground hover:opacity-90',
                ghost: 'bg-transparent text-muted-foreground hover:bg-accent hover:text-foreground',
                outline: 'border-border bg-transparent text-foreground hover:bg-accent',
            },
            size: {
                default: 'h-10 px-4',
                sm: 'h-8 px-3 text-xs',
                icon: 'h-8 w-8',
            },
        },
        defaultVariants: { variant: 'default', size: 'default' },
    },
);

export interface ButtonProps
    extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
    asChild?: boolean;
}

export function Button({
    className,
    variant,
    size,
    asChild = false,
    type = 'button',
    ...props
}: ButtonProps) {
    const Component = asChild ? Slot : 'button';
    return (
        <Component
            className={cn(buttonVariants({ variant, size }), className)}
            {...(asChild ? {} : { type })}
            {...props}
        />
    );
}
