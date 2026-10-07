package com.quancrypt.qbank.account.unit.facade;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.qbank.account.facade.AccountFacade;
import com.quancrypt.qbank.account.facade.AuthenticationFacade;
import com.quancrypt.qbank.account.facade.JwksFacade;
import com.quancrypt.qbank.account.facade.dto.AccountView;
import com.quancrypt.qbank.account.facade.dto.JwkView;
import com.quancrypt.qbank.account.facade.dto.LoginView;
import com.quancrypt.qbank.account.facade.error.BadRequestException;
import com.quancrypt.qbank.account.facade.error.ForbiddenException;
import com.quancrypt.qbank.account.facade.error.ResourceNotFoundException;
import com.quancrypt.qbank.account.facade.error.UnauthorizedException;
import com.quancrypt.qbank.account.port.inbound.AccountAccessDeniedException;
import com.quancrypt.qbank.account.port.inbound.AccountNotFoundException;
import com.quancrypt.qbank.account.port.inbound.AccountResult;
import com.quancrypt.qbank.account.port.inbound.AuthenticationResult;
import com.quancrypt.qbank.account.port.inbound.InvalidCredentialsException;
import com.quancrypt.qbank.account.port.inbound.InvalidRequestException;
import com.quancrypt.qbank.account.port.inbound.JwksResult;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.List;
import org.junit.jupiter.api.Test;

class FacadeTest {

    @Test
    void loginMapsTheResultAndAddsTheTokenType() {
        AuthenticationFacade facade = new AuthenticationFacade(command -> new AuthenticationResult("jwt", 900));

        assertThat(facade.login("demo1", "pw")).isEqualTo(new LoginView("jwt", "Bearer", 900));
    }

    @Test
    void loginTranslatesUseCaseErrors() {
        AuthenticationFacade invalid = new AuthenticationFacade(command -> {
            throw new InvalidRequestException("missing");
        });
        AuthenticationFacade wrong = new AuthenticationFacade(command -> {
            throw new InvalidCredentialsException();
        });

        assertThatThrownBy(() -> invalid.login("a", "b")).isInstanceOf(BadRequestException.class);
        assertThatThrownBy(() -> wrong.login("a", "b")).isInstanceOf(UnauthorizedException.class);
    }

    @Test
    void accountBalanceIsRenderedAsAPlainDecimalString() {
        AccountFacade facade = new AccountFacade(query -> new AccountResult(
                query.accountId(), "Demo User 1", "TRY", new BigDecimal("10000.00")));

        assertThat(facade.getAccount("acc-001", "demo1"))
                .isEqualTo(new AccountView("acc-001", "Demo User 1", "TRY", "10000.00"));
    }

    @Test
    void accountTranslatesUseCaseErrors() {
        AccountFacade invalid = new AccountFacade(query -> {
            throw new InvalidRequestException("bad id");
        });
        AccountFacade missing = new AccountFacade(query -> {
            throw new AccountNotFoundException();
        });
        AccountFacade denied = new AccountFacade(query -> {
            throw new AccountAccessDeniedException();
        });

        assertThatThrownBy(() -> invalid.getAccount("x", "u")).isInstanceOf(BadRequestException.class);
        assertThatThrownBy(() -> missing.getAccount("x", "u")).isInstanceOf(ResourceNotFoundException.class);
        assertThatThrownBy(() -> denied.getAccount("x", "u")).isInstanceOf(ForbiddenException.class);
    }

    @Test
    void jwksEncodesModulusAndExponentAsUnsignedBase64Url() {
        // modulus with a leading zero byte in two's complement form; 65537 must become "AQAB"
        BigInteger modulus = new BigInteger("00ff00ff", 16);
        JwksFacade facade = new JwksFacade(() -> new JwksResult(List.of(
                new JwksResult.Key("kid-1", modulus, BigInteger.valueOf(65537)))));

        List<JwkView> keys = facade.getJwks().keys();

        assertThat(keys).containsExactly(new JwkView("RSA", "sig", "RS256", "kid-1", "_wD_", "AQAB"));
    }
}
