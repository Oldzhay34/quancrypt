package com.quancrypt.qbank.payment.facade.dto;

/** The authenticated caller as the api layer knows it: token subject and the bearer token itself. */
public record CallerView(String username, String bearerToken) {

    @Override
    public String toString() {
        return "CallerView[username=" + username + ", bearerToken=****]";
    }
}
