/**
 * The two fixed refusal sentences (crypto-domain section 4, word for word; the service never lets a model write them). The
 * `refusal` event carries the text itself; a refusal loaded from the history is only an ordinary assistant message, so it is
 * recognised by these sentences (D-292).
 */
export const REFUSAL_TEXTS: readonly string[] = [
    'Bahsettiğiniz şeyi anlamadım; yalnızca projenizdeki şifreleme ve kuantum-güvenli geçiş konularında yardımcı olabiliyorum.',
    "I didn't understand what you mentioned; I can only help with encryption in your project and quantum-safe migration.",
];

export function isRefusalText(text: string): boolean {
    return REFUSAL_TEXTS.includes(text.trim());
}
