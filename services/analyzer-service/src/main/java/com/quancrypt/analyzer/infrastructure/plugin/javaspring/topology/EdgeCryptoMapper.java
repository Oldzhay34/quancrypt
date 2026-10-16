package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.quancrypt.analyzer.domain.model.CryptoUsage;
import com.quancrypt.analyzer.domain.model.Evidence;
import com.quancrypt.analyzer.domain.model.FindingRef;
import com.quancrypt.analyzer.domain.model.KeyExchange;
import com.quancrypt.analyzer.domain.model.LineRange;
import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.domain.model.ServiceEdge;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.NameSanitizer;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectIndex;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.pem.PemFacts;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ssl.SslBundle;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.TreeSet;

/**
 * Maps the crypto of a connection onto its edge: whether it is TLS and mutual TLS, which crypto findings it uses, and the key
 * exchange its Java version offers.
 *
 * <p>TLS: the evidence says so (a secure URL scheme) or the target listens with a certificate. Mutual TLS: TLS, the target asks
 * clients for a certificate (Spring {@code client-auth: need|want}, Mosquitto {@code require_certificate true}) and the client has
 * an identity: an SSL bundle with a key store, or a mounted certificate with its key. A client without an identity found by
 * the detectors uses the module's only client bundle if it has exactly one; with several it has none (mutual TLS is not
 * claimed without evidence).
 *
 * <p>Findings: those at the lines where the connection was seen, the findings of the SSL bundles on both sides and of the
 * certificate files of both sides, and the TLS findings of the Java files that build the connection. The usages are indexed by
 * file once, so an edge looks only at the files it is about.
 */
final class EdgeCryptoMapper {

    private static final Set<UsageContext> TLS_CONTEXTS = Set.of(UsageContext.TLS_KEY_EXCHANGE, UsageContext.TLS_SERVER_AUTH,
            UsageContext.MTLS_CLIENT_AUTH, UsageContext.CERTIFICATE);

    /** What was found for one edge. */
    record Result(boolean tls, boolean mtls, List<FindingRef> findings, Optional<KeyExchange> keyExchange) {
    }

    private final TopologyContext context;
    private final Map<RelativePath, List<CryptoUsage>> usagesByFile = new HashMap<>();
    private final Map<String, Set<String>> candidateBundles = new HashMap<>();
    private final Map<String, Optional<KeyExchange>> namedGroups = new HashMap<>();

    EdgeCryptoMapper(TopologyContext context, List<CryptoUsage> usages) {
        this.context = context;
        for (CryptoUsage usage : usages) {
            usagesByFile.computeIfAbsent(usage.evidence().file(), f -> new ArrayList<>()).add(usage);
        }
    }

    Result map(TopologyAssembler.MergedEdge edge, TNode source, TNode target) {
        Listener listener = target.listenerFor(edge.targetPort());
        boolean tls = edge.tls() || listener.tls();
        ProjectIndex index = context.index();
        Set<SslBundle> clientBundles = clientBundles(edge, source);
        boolean identity = !clientBundles.isEmpty() || !edge.certificates().isEmpty();
        boolean mtls = tls && listener.asksForClientCertificate() && identity;

        List<FindingRef> findings = new ArrayList<>();
        if (tls) {
            Set<SslBundle> bundles = new LinkedHashSet<>(clientBundles);
            listener.serverBundle().flatMap(index.bundles()::get).ifPresent(bundles::add);
            Set<RelativePath> certificateFiles = new TreeSet<>(Comparator.comparing(RelativePath::value));
            for (SslBundle bundle : bundles) {
                bundle.keystoreReferences().forEach(ref -> certificate(index, ref).ifPresent(certificateFiles::add));
            }
            edge.certificates().forEach(ref -> certificate(index, ref).ifPresent(certificateFiles::add));
            listener.certificateFiles().forEach(ref -> certificate(index, ref).ifPresent(certificateFiles::add));
            List<Evidence> seen = new ArrayList<>(edge.evidence());
            seen.addAll(listener.evidence());
            findings.addAll(findings(seen, certificateFiles, bundles));
        }
        Optional<KeyExchange> exchange = tls ? keyExchange(source) : Optional.empty();
        return new Result(tls, mtls, findings, exchange);
    }

    private List<FindingRef> findings(List<Evidence> seen, Set<RelativePath> certificateFiles, Set<SslBundle> bundles) {
        Set<RelativePath> files = new TreeSet<>(Comparator.comparing(RelativePath::value));
        files.addAll(certificateFiles);
        bundles.forEach(b -> files.add(b.file()));
        seen.forEach(e -> files.add(e.file()));
        List<CryptoUsage> related = new ArrayList<>();
        for (RelativePath file : files) {
            for (CryptoUsage usage : usagesByFile.getOrDefault(file, List.of())) {
                if (related(usage, seen, certificateFiles, bundles)) {
                    related.add(usage);
                }
            }
        }
        related.sort(order());
        Set<FindingRef> unique = new LinkedHashSet<>();
        related.forEach(u -> unique.add(FindingRef.of(u)));
        return unique.stream().limit(ServiceEdge.MAX_FINDINGS).toList();
    }

    private Set<SslBundle> clientBundles(TopologyAssembler.MergedEdge edge, TNode source) {
        ProjectIndex index = context.index();
        Optional<String> serverBundle = source.listener.serverBundle();
        Set<SslBundle> found = new LinkedHashSet<>();
        for (String name : edge.bundles()) {
            index.bundles().get(name).filter(SslBundle::hasIdentity).filter(b -> !serverBundle.equals(Optional.of(b.name()))).ifPresent(found::add);
        }
        if (!found.isEmpty() || !edge.certificates().isEmpty() || source.module.isEmpty()) {
            return found;
        }
        Module module = source.module.get();
        Set<String> candidates = candidateBundles.computeIfAbsent(module.dir(), dir -> {
            Set<String> names = new LinkedHashSet<>(ConfigUrls.configuredBundles(module));
            names.addAll(context.facts().bundles(module));
            return names;
        });
        List<SslBundle> withIdentity = candidates.stream().map(n -> index.bundles().get(n)).flatMap(Optional::stream).filter(SslBundle::hasIdentity)
                .filter(b -> !serverBundle.equals(Optional.of(b.name()))).toList();
        if (withIdentity.size() == 1) {
            found.add(withIdentity.get(0));
        }
        return found;
    }

    private static Optional<RelativePath> certificate(ProjectIndex index, String reference) {
        return index.pem().byBasename(ProjectIndex.basename(reference)).map(PemFacts::file);
    }

    private static boolean related(CryptoUsage usage, List<Evidence> seen, Set<RelativePath> certificateFiles, Set<SslBundle> bundles) {
        RelativePath file = usage.evidence().file();
        if (certificateFiles.contains(file) && usage.evidence().lines().isEmpty()) {
            return true;
        }
        if (!TLS_CONTEXTS.contains(usage.usageContext())) {
            return false;
        }
        for (SslBundle bundle : bundles) {
            if (bundle.file().equals(file) && usage.symbol().equals(NameSanitizer.clean("spring.ssl.bundle." + bundle.type() + "." + bundle.name()))) {
                return true;
            }
        }
        for (Evidence evidence : seen) {
            if (!evidence.file().equals(file)) {
                continue;
            }
            if (evidence.locationKind() == LocationKind.CODE) {
                if (usage.usageContext() == UsageContext.TLS_KEY_EXCHANGE) {
                    return true;
                }
            } else if (inside(usage, evidence.lines())) {
                return true;
            }
        }
        return false;
    }

    private static boolean inside(CryptoUsage usage, Optional<LineRange> range) {
        return range.isPresent() && usage.evidence().lines().filter(l -> l.start() >= range.get().start() && l.start() <= range.get().end()).isPresent();
    }

    private static Comparator<CryptoUsage> order() {
        return Comparator.comparing((CryptoUsage u) -> u.evidence().file().value())
                .thenComparingInt(u -> u.evidence().lines().map(LineRange::start).orElse(0)).thenComparing(CryptoUsage::symbol)
                .thenComparing(u -> u.algorithm().family().name()).thenComparing(u -> u.usageContext().name());
    }

    /** Groups the code or the configuration names win over the inference from the Java version. */
    private Optional<KeyExchange> keyExchange(TNode source) {
        if (source.module.isEmpty()) {
            return Optional.empty();
        }
        Module module = source.module.get();
        return namedGroups.computeIfAbsent(module.dir(), dir -> named(module)).or(() -> JdkTlsDefaults.inferred(module.javaVersion()));
    }

    /** The groups a module names itself: the {@code jdk.tls.namedGroups} configuration key, else the constant list its code sets. */
    private Optional<KeyExchange> named(Module module) {
        Optional<String> configured = module.config().value(ModuleFacts.GROUPS_PROPERTY).filter(v -> !v.isEmpty()).or(() -> context.facts().groups(module));
        return configured.flatMap(list -> JdkTlsDefaults.named(list, module.javaVersion()));
    }
}
