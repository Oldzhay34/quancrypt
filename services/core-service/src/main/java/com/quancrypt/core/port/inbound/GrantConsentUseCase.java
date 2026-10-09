package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.ConsentView;

/** Grants or re-grants a consent. */
public interface GrantConsentUseCase {

    ConsentView execute(GrantConsentCommand input);
}
