package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.ConsentListView;

/** Lists a project's consents. */
public interface GetConsentsUseCase {

    ConsentListView execute(GetConsentsQuery input);
}
