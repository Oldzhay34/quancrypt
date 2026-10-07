package com.quancrypt.qbank.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/** QBank gateway: routes and TLS settings only, configured in application.yml (D-06, D-109). */
@SpringBootApplication
public class QbankGatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(QbankGatewayApplication.class, args);
    }
}
