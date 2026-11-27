import { motion } from 'framer-motion';
import { Menu, PanelLeftClose, PanelLeftOpen, X } from 'lucide-react';
import { useState } from 'react';
import type { KeyboardEvent, ReactNode } from 'react';
import { NavLink } from 'react-router';
import { cn } from '@/lib/utils';

export interface SidebarItem {
    to: string;
    label: string;
    icon: ReactNode;
}

export interface SidebarLabels {
    nav: string;
    open: string;
    close: string;
    collapse: string;
    expand: string;
}

/**
 * The app's one sidebar (adapted from the given sidebar component, D-348b, D-356b): brand, an action, the pages, a free
 * area (the chat history) and a footer. A button folds it to icons on wide screens; on narrow screens a menu button opens
 * it. One `nav` element serves both, and the labels stay in the document so every control keeps its name.
 */
export function Sidebar({
    brand,
    items,
    footer,
    labels,
    action,
    children,
}: {
    brand: string;
    items: SidebarItem[];
    footer?: (collapsed: boolean, close: () => void) => ReactNode;
    labels: SidebarLabels;
    action?: (collapsed: boolean, close: () => void) => ReactNode;
    children?: (close: () => void) => ReactNode;
}) {
    const [collapsed, setCollapsed] = useState(false);
    const [mobileOpen, setMobileOpen] = useState(false);
    const close = () => setMobileOpen(false);
    const onKeyDown = (event: KeyboardEvent) => {
        if (event.key === 'Escape') close();
    };

    const link = (item: SidebarItem) => (
        <NavLink
            key={item.to}
            to={item.to}
            title={item.label}
            onClick={close}
            className={({ isActive }) =>
                cn(
                    'flex shrink-0 items-center gap-3 overflow-hidden rounded-lg px-2 py-2 text-sm whitespace-nowrap text-foreground no-underline hover:bg-accent',
                    isActive && 'bg-accent font-semibold shadow-[inset_3px_0_0_var(--highlight)]',
                )
            }
        >
            <span aria-hidden="true" className="flex h-5 w-5 shrink-0 items-center justify-center">
                {item.icon}
            </span>
            <motion.span
                initial={false}
                animate={{ opacity: collapsed ? 0 : 1 }}
                className="max-md:!opacity-100"
            >
                {item.label}
            </motion.span>
        </NavLink>
    );

    return (
        <div className="print:hidden md:flex md:h-full md:flex-col" onKeyDown={onKeyDown}>
            <button
                type="button"
                className="m-2 inline-flex cursor-pointer items-center gap-2 rounded-md border border-border bg-card p-2 text-foreground md:hidden"
                aria-expanded={mobileOpen}
                onClick={() => setMobileOpen((value) => !value)}
            >
                {mobileOpen ? (
                    <X aria-hidden="true" className="h-5 w-5" />
                ) : (
                    <Menu aria-hidden="true" className="h-5 w-5" />
                )}
                <span className="sr-only">{mobileOpen ? labels.close : labels.open}</span>
            </button>
            <nav
                aria-label={labels.nav}
                className={cn(
                    'min-h-0 flex-col gap-1 border-r border-border bg-card px-2 py-3 transition-[width] duration-200 md:flex md:h-full',
                    collapsed ? 'md:w-14' : 'md:w-64',
                    mobileOpen ? 'flex max-h-[75vh]' : 'hidden',
                )}
            >
                <div className="flex items-center justify-between gap-2 px-1 pb-2">
                    <strong className={cn('truncate text-base', collapsed && 'md:sr-only')}>{brand}</strong>
                    <button
                        type="button"
                        aria-label={collapsed ? labels.expand : labels.collapse}
                        title={collapsed ? labels.expand : labels.collapse}
                        onClick={() => setCollapsed((value) => !value)}
                        className="hidden shrink-0 cursor-pointer rounded-md border-0 bg-transparent p-1 text-muted-foreground hover:bg-accent md:inline-flex"
                    >
                        {collapsed ? (
                            <PanelLeftOpen aria-hidden="true" className="h-5 w-5" />
                        ) : (
                            <PanelLeftClose aria-hidden="true" className="h-5 w-5" />
                        )}
                    </button>
                </div>
                {action?.(collapsed, close)}
                {items.map(link)}
                <div className={cn('flex min-h-0 flex-1 flex-col pt-3', collapsed && 'md:invisible')}>
                    {children?.(close)}
                </div>
                {footer?.(collapsed, close)}
            </nav>
        </div>
    );
}
