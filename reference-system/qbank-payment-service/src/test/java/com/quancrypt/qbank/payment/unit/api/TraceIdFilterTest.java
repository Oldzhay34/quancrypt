package com.quancrypt.qbank.payment.unit.api;

import static org.assertj.core.api.Assertions.assertThat;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import com.quancrypt.qbank.payment.api.TraceIdFilter;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

class TraceIdFilterTest {

    private final TraceIdFilter filter = new TraceIdFilter();

    private String run(String incomingHeader, AtomicReference<String> mdcInsideChain) throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest();
        if (incomingHeader != null) {
            request.addHeader(TraceIdFilter.HEADER, incomingHeader);
        }
        MockHttpServletResponse response = new MockHttpServletResponse();
        filter.doFilter(request, response, new MockFilterChain() {
            @Override
            public void doFilter(jakarta.servlet.ServletRequest req, jakarta.servlet.ServletResponse res) {
                mdcInsideChain.set(MDC.get(TraceIdFilter.MDC_KEY));
            }
        });
        return response.getHeader(TraceIdFilter.HEADER);
    }

    @Test
    void aSafeIncomingIdIsKeptAndPutInTheLoggingContext() throws Exception {
        AtomicReference<String> inside = new AtomicReference<>();

        String header = run("trace-1.2_3", inside);

        assertThat(header).isEqualTo("trace-1.2_3");
        assertThat(inside.get()).isEqualTo("trace-1.2_3");
        assertThat(MDC.get(TraceIdFilter.MDC_KEY)).isNull();
    }

    @Test
    void aMissingIdIsReplacedByAGeneratedUuid() throws Exception {
        AtomicReference<String> inside = new AtomicReference<>();

        String header = run(null, inside);

        assertThat(header).matches("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}");
        assertThat(inside.get()).isEqualTo(header);
    }

    @Test
    void logsOneLinePerRequestThatCarriesTheTraceIdButNeverThePath() throws Exception {
        Logger logger = (Logger) LoggerFactory.getLogger(TraceIdFilter.class);
        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);
        try {
            MockHttpServletRequest request = new MockHttpServletRequest("GET", "/secret/path");
            request.setQueryString("token=abc");
            request.addHeader(TraceIdFilter.HEADER, "t-42");
            filter.doFilter(request, new MockHttpServletResponse(), new MockFilterChain());

            assertThat(appender.list).hasSize(1);
            ILoggingEvent event = appender.list.get(0);
            assertThat(event.getMDCPropertyMap()).containsEntry(TraceIdFilter.MDC_KEY, "t-42");
            assertThat(event.getFormattedMessage()).contains("method=GET").contains("status=200")
                    .doesNotContain("secret").doesNotContain("token");
        } finally {
            logger.detachAppender(appender);
        }
    }

    @Test
    void unsafeIdsAreReplaced() throws Exception {
        for (String unsafe : new String[] {"has space", "inject\"quote", "x".repeat(129), "{json}", ""}) {
            String header = run(unsafe, new AtomicReference<>());
            assertThat(header).isNotEqualTo(unsafe).matches("[0-9a-f-]{36}");
        }
    }
}
