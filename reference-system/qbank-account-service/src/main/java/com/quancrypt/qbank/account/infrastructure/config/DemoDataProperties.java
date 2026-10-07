package com.quancrypt.qbank.account.infrastructure.config;

import java.math.BigDecimal;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

/** Demo accounts and users loaded from demo-data.yaml; passwords appear only as BCrypt hashes. */
@ConfigurationProperties("qbank.demo")
public record DemoDataProperties(List<DemoAccount> accounts, List<DemoUser> users) {

    public DemoDataProperties {
        accounts = accounts == null ? List.of() : List.copyOf(accounts);
        users = users == null ? List.of() : List.copyOf(users);
    }

    /** A demo account. */
    public record DemoAccount(String accountId, String ownerName, String currency, BigDecimal balance) {
    }

    /** A demo user with the BCrypt hash of the user's password and the account the user owns. */
    public record DemoUser(String username, String passwordHash, String accountId) {

        @Override
        public String toString() {
            return "DemoUser[username=" + username + ", passwordHash=****, accountId=" + accountId + "]";
        }
    }
}
