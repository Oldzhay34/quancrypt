package com.quancrypt.core.port.inbound.view;

import java.util.List;

/** The consents of a project. */
public record ConsentListView(List<ConsentView> items) {

    public ConsentListView {
        items = List.copyOf(items);
    }
}
