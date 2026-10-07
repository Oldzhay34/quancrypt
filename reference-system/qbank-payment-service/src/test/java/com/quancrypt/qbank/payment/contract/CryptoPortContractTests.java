package com.quancrypt.qbank.payment.contract;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.qbank.payment.domain.model.CardToken;
import com.quancrypt.qbank.payment.domain.model.ReceiptSignature;
import com.quancrypt.qbank.payment.infrastructure.crypto.PemKeyLoader;
import com.quancrypt.qbank.payment.infrastructure.crypto.RsaOaepCardTokenizer;
import com.quancrypt.qbank.payment.infrastructure.crypto.Sha1WithRsaReceiptSigner;
import com.quancrypt.qbank.payment.port.outbound.CardTokenizer;
import com.quancrypt.qbank.payment.port.outbound.ReceiptSigner;
import com.quancrypt.qbank.payment.support.Fakes.FakeCardTokenizer;
import com.quancrypt.qbank.payment.support.Fakes.FakeReceiptSigner;
import com.quancrypt.qbank.payment.support.TestCertificates;
import org.junit.jupiter.api.Test;

/** Contract of CardTokenizer: every implementation must pass (Liskov substitution). */
abstract class CardTokenizerContractTest {

    abstract CardTokenizer create();

    @Test
    void producesANonBlankTokenThatIsNotTheCardNumber() {
        CardToken token = create().tokenize("4111111111111111");

        assertThat(token.value()).isNotBlank().isNotEqualTo("4111111111111111");
    }

    @Test
    void differentCardNumbersGiveDifferentTokens() {
        CardTokenizer tokenizer = create();

        assertThat(tokenizer.tokenize("4111111111111111")).isNotEqualTo(tokenizer.tokenize("5555555555554444"));
    }

    @Test
    void rejectsBlankAndMissingCardNumbers() {
        CardTokenizer tokenizer = create();

        assertThatThrownBy(() -> tokenizer.tokenize(" ")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> tokenizer.tokenize(null)).isInstanceOf(IllegalArgumentException.class);
    }
}

class FakeCardTokenizerContractTest extends CardTokenizerContractTest {

    @Override
    CardTokenizer create() {
        return new FakeCardTokenizer();
    }
}

class RsaOaepCardTokenizerContractTest extends CardTokenizerContractTest {

    @Override
    CardTokenizer create() {
        return new RsaOaepCardTokenizer(PemKeyLoader.loadPublicKey(TestCertificates.file("card-token.pub.pem")));
    }
}

/** Contract of ReceiptSigner: every implementation must pass (Liskov substitution). */
abstract class ReceiptSignerContractTest {

    abstract ReceiptSigner create();

    @Test
    void signsATextAndNamesTheAlgorithmAndTheKey() {
        ReceiptSignature signature = create().sign("some receipt text");

        assertThat(signature.algorithm()).isNotBlank();
        assertThat(signature.keyId()).isNotBlank();
        assertThat(signature.signature()).isNotBlank();
    }

    @Test
    void differentTextsGetDifferentSignatures() {
        ReceiptSigner signer = create();

        assertThat(signer.sign("text one").signature()).isNotEqualTo(signer.sign("text two").signature());
    }

    @Test
    void rejectsBlankAndMissingText() {
        ReceiptSigner signer = create();

        assertThatThrownBy(() -> signer.sign(" ")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> signer.sign(null)).isInstanceOf(IllegalArgumentException.class);
    }
}

class FakeReceiptSignerContractTest extends ReceiptSignerContractTest {

    @Override
    ReceiptSigner create() {
        return new FakeReceiptSigner();
    }
}

class Sha1WithRsaReceiptSignerContractTest extends ReceiptSignerContractTest {

    @Override
    ReceiptSigner create() {
        return new Sha1WithRsaReceiptSigner(
                PemKeyLoader.loadPrivateKey(TestCertificates.file("receipt-signing.key.pem")), "kid");
    }
}
