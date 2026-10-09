package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.FindingView;
import com.quancrypt.core.port.inbound.view.PageView;

/** Lists findings of a scan. */
public interface ListFindingsUseCase {

    PageView<FindingView> execute(ListFindingsQuery input);
}
