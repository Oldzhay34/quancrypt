package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.PageView;
import com.quancrypt.core.port.inbound.view.ScanView;

/** Lists a project's scans. */
public interface ListScansUseCase {

    PageView<ScanView> execute(ListScansQuery input);
}
