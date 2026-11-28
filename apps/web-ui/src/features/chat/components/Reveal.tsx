import { motion, useReducedMotion } from 'framer-motion';
import type { ReactNode } from 'react';

/** Lets a part of a screen arrive after the ones above it (D-361b); at once for a user who asked for less motion. */
export function Reveal({ order, children }: { order: number; children: ReactNode }) {
    const still = useReducedMotion();
    return (
        <motion.div
            initial={still ? false : { opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: order * 0.25, ease: 'easeOut' }}
        >
            {children}
        </motion.div>
    );
}
