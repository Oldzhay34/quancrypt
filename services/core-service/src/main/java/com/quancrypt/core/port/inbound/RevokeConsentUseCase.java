package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.ConsentView;

/** Revokes a consent and tells the warehouse. */
public interface RevokeConsentUseCase {

    ConsentView execute(RevokeConsentCommand input);
}
