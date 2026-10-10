package com.quancrypt.core.contract;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.core.domain.model.CallSite;
import com.quancrypt.core.domain.model.Finding;
import com.quancrypt.core.domain.model.FindingDetail;
import com.quancrypt.core.domain.model.LocationKind;
import com.quancrypt.core.domain.model.NodeKind;
import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.domain.model.Protocol;
import com.quancrypt.core.domain.model.ServiceLink;
import com.quancrypt.core.domain.model.ServiceNode;
import com.quancrypt.core.domain.model.SourceFile;
import com.quancrypt.core.domain.model.Topology;
import com.quancrypt.core.port.outbound.FindingContext;
import com.quancrypt.core.port.outbound.FindingFilter;
import com.quancrypt.core.port.outbound.FindingStats;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.stream.IntStream;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

/** SourceFileReader, SourceFileWriter, FindingReader, FindingWriter and PlanningContextReader. */
public abstract class FindingPortsContract extends PortContract {

    private static final FindingFilter NO_FILTER = new FindingFilter(Optional.empty(), Optional.empty(), Optional.empty(),
            Optional.empty(), Optional.empty());

    @Test
    void sourceFilesAreFoundByPathAndId() {
        Tree tree = tree();
        SourceFile config = file(tree.scan().id(), "src/main/resources/application.yml", LocationKind.CONFIG);

        assertThat(ports.sourceFileReader().byPaths(tree.scan().id(), List.of("src/main/resources/application.yml", "missing")))
                .containsExactlyEntriesOf(Map.of(config.path(), config));
        assertThat(ports.sourceFileReader().byPaths(tree.scan().id(), List.of())).isEmpty();
        assertThat(ports.sourceFileReader().find(tree.file().id())).contains(tree.file());
        assertThat(ports.sourceFileReader().byIds(List.of(tree.file().id(), config.id(), UUID.randomUUID())))
                .containsOnlyKeys(tree.file().id(), config.id());
    }

    /** A topology may bring up to 100 000 call-site paths (D-145c); the lookup must not depend on the driver's bind limit. */
    @Test
    void pathLookupAcceptsMoreValuesThanTheDriverBindLimit() {
        Tree tree = tree();
        List<String> paths = new ArrayList<>(IntStream.range(0, 40_000).mapToObj(i -> "src/gen/F" + i + ".java").toList());
        paths.add(tree.file().path());

        assertThat(ports.sourceFileReader().byPaths(tree.scan().id(), paths)).containsOnlyKeys(tree.file().path());
        assertThat(ports.sourceFileReader().byIds(Stream.concat(
                Stream.generate(UUID::randomUUID).limit(40_000), Stream.of(tree.file().id())).toList()))
                .containsOnlyKeys(tree.file().id());
    }

    @Test
    void duplicatesAreSkippedAndOnlyNewIdsReturned() {
        Tree tree = tree();
        Finding a = finding(tree.file().id(), "Tls#a", Priority.P1, 10);
        Finding aAgain = finding(tree.file().id(), "Tls#a", Priority.P1, 10);
        Finding noLine = finding(tree.file().id(), "Tls#b", Priority.P1, null);
        Finding noLineAgain = finding(tree.file().id(), "Tls#b", Priority.P1, null);

        List<UUID> first = ports.findingWriter().insertIgnoringDuplicates(List.of(a, aAgain, noLine));
        List<UUID> second = ports.findingWriter().insertIgnoringDuplicates(List.of(noLineAgain));

        assertThat(first).containsExactly(a.id(), noLine.id());
        assertThat(second).isEmpty();
        assertThat(ports.findingReader().countByScan(tree.scan().id())).isEqualTo(2);
        assertThat(ports.findingReader().find(a.id())).contains(new FindingDetail(a, tree.file()));
    }

    @Test
    void pageFiltersAndCounts() {
        Tree tree = tree();
        SourceFile test = file(tree.scan().id(), "src/test/java/TlsTest.java", LocationKind.TEST_CODE);
        Finding p1 = finding(tree.file().id(), "Tls#a", Priority.P1, 10);
        Finding p3 = finding(tree.file().id(), "Tls#b", Priority.P3, 20);
        Finding inTest = finding(test.id(), "TlsTest#c", Priority.P1, 5);
        ports.findingWriter().insertIgnoringDuplicates(List.of(p1, p3, inTest));

        FindingFilter onlyP1 = new FindingFilter(Optional.of(Priority.P1), Optional.empty(), Optional.empty(), Optional.empty(), Optional.empty());
        FindingFilter onlyTests = new FindingFilter(Optional.empty(), Optional.empty(), Optional.empty(), Optional.of(LocationKind.TEST_CODE),
                Optional.empty());

        assertThat(ports.findingReader().page(tree.scan().id(), onlyP1, 0, 10).items())
                .extracting(d -> d.finding().id()).containsExactlyInAnyOrder(p1.id(), inTest.id());
        assertThat(ports.findingReader().page(tree.scan().id(), onlyTests, 0, 10).items())
                .extracting(d -> d.finding().id()).containsExactly(inTest.id());
        assertThat(ports.findingReader().page(tree.scan().id(), NO_FILTER, 0, 2).total()).isEqualTo(3);
        assertThat(ports.findingReader().page(tree.scan().id(), NO_FILTER, 0, 2).items()).hasSize(2);
        assertThat(ports.findingReader().listByScan(tree.scan().id()))
                .extracting(d -> d.finding().id()).containsExactlyInAnyOrder(p1.id(), p3.id(), inTest.id());
    }

    @Test
    void statsCountByPriorityAlgorithmAndLocationKind() {
        Tree tree = tree();
        SourceFile test = file(tree.scan().id(), "src/test/java/TlsTest.java", LocationKind.TEST_CODE);
        ports.findingWriter().insertIgnoringDuplicates(List.of(
                finding(tree.file().id(), "Tls#a", Priority.P1, 10),
                finding(tree.file().id(), "Tls#b", Priority.P3, 20),
                finding(test.id(), "TlsTest#c", Priority.P1, 5)));

        FindingStats stats = ports.findingReader().stats(tree.scan().id());

        assertThat(stats.total()).isEqualTo(3);
        assertThat(stats.byPriority()).containsExactlyInAnyOrderEntriesOf(Map.of(Priority.P1, 2, Priority.P3, 1));
        assertThat(stats.byAlgorithmFamily()).hasSize(1).containsValue(3);
        assertThat(stats.byLocationKind()).containsExactlyInAnyOrderEntriesOf(Map.of(LocationKind.CODE, 2, LocationKind.TEST_CODE, 1));
    }

    @Test
    void unreferencedFilesAreDeleted() {
        Tree tree = tree();
        SourceFile orphan = file(tree.scan().id(), "src/main/java/Unused.java", LocationKind.CODE);
        ports.findingWriter().insertIgnoringDuplicates(List.of(finding(tree.file().id(), "Tls#a", Priority.P1, 10)));

        assertThat(ports.sourceFileWriter().deleteUnreferenced(tree.scan().id())).isEqualTo(1);
        assertThat(ports.sourceFileReader().find(orphan.id())).isEmpty();
        assertThat(ports.sourceFileReader().find(tree.file().id())).isPresent();
    }

    @Test
    void planningContextKnowsDeviceLinksAndCallSites() {
        Tree tree = tree();
        Finding onDevice = finding(tree.file().id(), "Tls#a", Priority.P1, 10);
        Finding plain = finding(tree.file().id(), "Tls#b", Priority.P1, 20);
        Finding unlinked = finding(tree.file().id(), "Tls#c", Priority.P1, 30);
        ports.findingWriter().insertIgnoringDuplicates(List.of(onDevice, plain, unlinked));
        ServiceNode service = new ServiceNode(ids.next(), "payment", NodeKind.SERVICE);
        ServiceNode broker = new ServiceNode(ids.next(), "mosquitto", NodeKind.BROKER);
        ServiceNode device = new ServiceNode(ids.next(), "terminal", NodeKind.DEVICE);
        ServiceLink deviceLink = new ServiceLink(ids.next(), device.id(), broker.id(), Protocol.MQTT, true, true,
                List.of(new CallSite(tree.file().id(), 1, 2), new CallSite(tree.file().id(), 5, 6)), Set.of(onDevice.id()));
        ServiceLink serviceLink = new ServiceLink(ids.next(), service.id(), broker.id(), Protocol.MQTT, true, true,
                List.of(new CallSite(tree.file().id(), 8, 9)), Set.of(onDevice.id(), plain.id()));
        ports.topologyWriter().insert(new Topology(ids.next(), tree.scan().id(), at(3), List.of(service, broker, device),
                List.of(deviceLink, serviceLink)));

        Map<UUID, FindingContext> context = ports.planningContext().load(tree.scan().id());

        assertThat(context).containsExactlyInAnyOrderEntriesOf(Map.of(
                onDevice.id(), new FindingContext(true, 3),
                plain.id(), new FindingContext(false, 1),
                unlinked.id(), new FindingContext(false, 0)));
    }
}
