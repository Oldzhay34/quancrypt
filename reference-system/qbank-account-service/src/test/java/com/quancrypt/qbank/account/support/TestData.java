package com.quancrypt.qbank.account.support;

import com.quancrypt.qbank.account.domain.model.Account;
import com.quancrypt.qbank.account.domain.model.AccountId;
import com.quancrypt.qbank.account.domain.model.UserCredential;
import java.math.BigDecimal;
import java.time.Instant;

/** Small fixed data set for tests. */
public final class TestData {

    public static final Instant NOW = Instant.parse("2026-10-07T10:00:00Z");

    public static final AccountId ACC_1 = new AccountId("acc-001");
    public static final AccountId ACC_2 = new AccountId("acc-002");

    public static final Account ACCOUNT_1 = new Account(ACC_1, "Demo User 1", "TRY", new BigDecimal("1000.00"));
    public static final Account ACCOUNT_2 = new Account(ACC_2, "Demo User 2", "TRY", new BigDecimal("2500.50"));

    public static final UserCredential USER_1 =
            new UserCredential("demo1", FakePasswordVerifier.hashOf("pw-1"), ACC_1);
    public static final UserCredential USER_2 =
            new UserCredential("demo2", FakePasswordVerifier.hashOf("pw-2"), ACC_2);

    private TestData() {
    }
}
