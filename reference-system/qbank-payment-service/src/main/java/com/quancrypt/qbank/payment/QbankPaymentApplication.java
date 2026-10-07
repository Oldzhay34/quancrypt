package com.quancrypt.qbank.payment;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/** Entry point of the QBank payment service. */
@SpringBootApplication
public class QbankPaymentApplication {

    public static void main(String[] args) {
        SpringApplication.run(QbankPaymentApplication.class, args);
    }
}
