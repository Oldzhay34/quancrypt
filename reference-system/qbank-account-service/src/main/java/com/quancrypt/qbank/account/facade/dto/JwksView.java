package com.quancrypt.qbank.account.facade.dto;

import java.util.List;

/** A JSON Web Key Set. */
public record JwksView(List<JwkView> keys) {

    public JwksView {
        keys = List.copyOf(keys);
    }
}
