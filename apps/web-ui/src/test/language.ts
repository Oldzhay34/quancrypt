import { screen } from '@testing-library/react';
import type userEvent from '@testing-library/user-event';

/** Picks the interface language the way a user does: in the sidebar's settings menu (D-360b). */
export async function chooseLanguage(user: ReturnType<typeof userEvent.setup>, name: 'Türkçe' | 'English') {
    await user.click(await screen.findByRole('button', { name: /^(Ayarlar|Settings)$/ }));
    await user.click(await screen.findByRole('menuitemradio', { name }));
}
