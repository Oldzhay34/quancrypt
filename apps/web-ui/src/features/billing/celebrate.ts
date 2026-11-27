import confetti from 'canvas-confetti';

/**
 * Confetti in the brand colours when a plan is picked. No web worker (the page's policy allows no blob: worker), and
 * nothing for a user who asked for less motion.
 */
export function celebrate(): void {
    const fire = confetti.create(undefined, {
        useWorker: false,
        resize: true,
        disableForReducedMotion: true,
    });
    void fire({
        particleCount: 90,
        spread: 70,
        startVelocity: 35,
        origin: { y: 0.65 },
        colors: ['#eaaa00', '#2557d6', '#dde3e8'],
    });
}
