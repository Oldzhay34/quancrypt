import js from '@eslint/js';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';
import tseslint from 'typescript-eslint';

// Layer rules (D-05 spirit for the UI, solid-checklist): shared depends on nothing above it; a feature sees only shared and
// the public barrel (index.ts) of another feature, never its internals; app wires everything. Relative paths may not climb out
// of a module either, so the rules cannot be bypassed with `../..`.
const noFeatureInternals = {
    group: ['@/features/*/*', '**/features/*/*'],
    message: 'Import another feature through its public index.ts only.',
};
const noApp = { group: ['@/app/*', '@/app'], message: 'A feature must not depend on app.' };
const sharedMayNotImport = {
    group: ['@/features/*', '@/features', '@/app/*', '@/app'],
    message: 'shared must not depend on features or app.',
};
const stayInModule = (pattern) => ({
    group: [pattern],
    message: 'A relative import may not leave its own module: use the @/ alias for other modules.',
});
const restrict = (...patterns) => ['error', { patterns }];

export default tseslint.config(
    { ignores: ['dist', 'node_modules', 'src/shared/api/generated'] },
    js.configs.recommended,
    ...tseslint.configs.recommended,
    reactHooks.configs.flat.recommended,
    {
        languageOptions: { globals: { ...globals.browser } },
        rules: { '@typescript-eslint/consistent-type-imports': 'error' },
    },
    {
        // src/shared/<module>/<file>: `../x` stays in shared, `../../x` would leave it.
        files: ['src/shared/*/*.{ts,tsx}'],
        rules: { 'no-restricted-imports': restrict(sharedMayNotImport, stayInModule('../../**')) },
    },
    {
        // src/features/<feature>/<file>: any `../x` reaches another feature or shared; the alias makes the dependency visible.
        files: ['src/features/*/*.{ts,tsx}'],
        rules: { 'no-restricted-imports': restrict(noApp, noFeatureInternals, stayInModule('../**')) },
    },
    {
        // src/features/<feature>/<folder>/<file>: `../x` stays in the feature, `../../x` would leave it.
        files: ['src/features/*/*/**/*.{ts,tsx}'],
        rules: { 'no-restricted-imports': restrict(noApp, noFeatureInternals, stayInModule('../../**')) },
    },
    {
        files: ['src/app/**/*.{ts,tsx}'],
        rules: { 'no-restricted-imports': restrict(noFeatureInternals) },
    },
    {
        files: ['**/*.test.{ts,tsx}', 'src/test/**'],
        rules: { 'no-restricted-imports': 'off' },
    },
);
