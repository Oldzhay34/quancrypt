package com.quancrypt.analyzer.evaluation;

import com.quancrypt.analyzer.domain.exception.UnsupportedProjectException;
import com.quancrypt.analyzer.domain.model.AllowedRoots;
import com.quancrypt.analyzer.domain.model.AnalysisRoot;
import com.quancrypt.analyzer.domain.model.CanonicalNames;
import com.quancrypt.analyzer.domain.model.CryptoUsage;
import com.quancrypt.analyzer.domain.model.ProjectDescriptor;
import com.quancrypt.analyzer.domain.model.ProjectType;
import com.quancrypt.analyzer.domain.policy.ProjectTypeDetector;
import com.quancrypt.analyzer.infrastructure.cbom.CycloneDxCbomWriter;
import com.quancrypt.analyzer.infrastructure.dictionary.CanonicalDictionaryLoader;
import com.quancrypt.analyzer.infrastructure.filesystem.FileSystemSourceTreeReader;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaSpringPlugin;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaSpringPlugins;
import com.quancrypt.analyzer.port.inbound.AnalysisView;
import com.quancrypt.analyzer.port.inbound.AnalyzeCryptoCommand;
import com.quancrypt.analyzer.port.outbound.CbomWriter;
import com.quancrypt.analyzer.port.outbound.Clock;
import com.quancrypt.analyzer.port.outbound.IdGenerator;
import com.quancrypt.analyzer.port.outbound.SourceTree;
import com.quancrypt.analyzer.usecase.AnalyzeCryptoService;
import com.quancrypt.analyzer.usecase.PluginSelector;
import com.quancrypt.analyzer.usecase.ProjectOpener;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;
import java.util.stream.Stream;

/**
 * Times the analysis of projects on the real file system (NFR-01: at most 5 minutes for about 50,000 lines, D-198). The
 * measurement runs in this process, without the HTTP layer; the first run is cold (class loading, JIT), the others show
 * the warm time, and no further run starts after one that took more than 100 seconds. A project with a build file at its
 * root goes through the whole use case (project type, plugin, detectors, CBOM). A directory of independent services has
 * none (D-203), so there the plugin and the CBOM writer run directly and the project type detection is left out. The peak
 * heap is sampled while the analysis runs.
 */
public final class PerformanceMeasurement {

    static final long TARGET_MS = 300_000;
    private static final long SLOW_RUN_MS = 100_000;
    private static final Set<String> SKIPPED_DIRECTORIES = Set.of(".git", ".gradle", ".idea", "node_modules", "build", "target");

    /** What was measured: the project's size, what the analysis found and how long each run took. */
    public record Result(String project, boolean wholeUseCase, long javaFiles, long javaLines, int filesScanned, int findings,
            List<Long> runsMs, long peakHeapMiB, long maxHeapMiB, int processors, String java) {

        public Result {
            runsMs = List.copyOf(runsMs);
        }

        public boolean withinTarget() {
            return runsMs.stream().allMatch(ms -> ms <= TARGET_MS);
        }
    }

    private record Counts(int filesScanned, int findings) {
    }

    private PerformanceMeasurement() {
    }

    public static Result measure(Path root, int runs) throws IOException {
        if (runs < 1) {
            throw new IllegalArgumentException("at least one run is needed");
        }
        Path real = root.toRealPath();
        CanonicalNames names = new CanonicalNames(new CanonicalDictionaryLoader().loadFromClasspath());
        Clock clock = Instant::now;
        IdGenerator ids = UUID::randomUUID;
        JavaSpringPlugin plugin = JavaSpringPlugins.standard(names);
        CbomWriter writer = new CycloneDxCbomWriter(clock, ids, "perf");
        FileSystemSourceTreeReader reader = new FileSystemSourceTreeReader();
        boolean wholeUseCase = hasBuildFile(real);
        AnalyzeCryptoService service = new AnalyzeCryptoService(
                new ProjectOpener(new AllowedRoots(List.of(real.toString())), reader, new ProjectTypeDetector()),
                new PluginSelector(List.of(plugin)), writer, ids, clock);

        AtomicLong peak = new AtomicLong();
        Thread sampler = new Thread(() -> {
            Runtime runtime = Runtime.getRuntime();
            while (!Thread.currentThread().isInterrupted()) {
                peak.accumulateAndGet(runtime.totalMemory() - runtime.freeMemory(), Math::max);
                try {
                    Thread.sleep(50);
                } catch (InterruptedException e) {
                    return;
                }
            }
        }, "heap-sampler");
        sampler.setDaemon(true);
        sampler.start();
        List<Long> times = new ArrayList<>();
        Counts last = null;
        try {
            for (int i = 0; i < runs; i++) {
                Instant started = Instant.now();
                last = wholeUseCase ? viaUseCase(service, real) : viaPlugin(plugin, writer, reader, real);
                long ms = Duration.between(started, Instant.now()).toMillis();
                times.add(ms);
                if (ms > SLOW_RUN_MS) {
                    break;
                }
            }
        } finally {
            sampler.interrupt();
        }
        long[] size = javaSize(real);
        Runtime runtime = Runtime.getRuntime();
        return new Result(Objects.requireNonNull(real.getFileName(), "the root is not a directory with a name").toString(), wholeUseCase,
                size[0], size[1], last.filesScanned(), last.findings(), times, peak.get() / (1024 * 1024), runtime.maxMemory() / (1024 * 1024),
                runtime.availableProcessors(), System.getProperty("java.version"));
    }

    private static Counts viaUseCase(AnalyzeCryptoService service, Path root) {
        AnalysisView view = service.analyze(new AnalyzeCryptoCommand(root.toString(), true));
        return new Counts(view.stats().filesScanned(), view.findings().size());
    }

    private static Counts viaPlugin(JavaSpringPlugin plugin, CbomWriter writer, FileSystemSourceTreeReader reader, Path root) {
        AnalysisRoot analysisRoot = new AnalysisRoot(root.toString());
        SourceTree tree = reader.open(analysisRoot);
        List<CryptoUsage> usages = plugin.analyzeCrypto(tree);
        // The writer does not read the project; the type is only there because the descriptor needs one.
        writer.write(new ProjectDescriptor(analysisRoot, ProjectType.MAVEN), usages);
        return new Counts(tree.files().size(), usages.size());
    }

    private static boolean hasBuildFile(Path root) {
        try {
            new ProjectTypeDetector().detect(name -> Files.isRegularFile(root.resolve(name)));
            return true;
        } catch (UnsupportedProjectException e) {
            return false;
        }
    }

    /** The number of .java files and their lines, outside the directories the analysis skips as well. */
    static long[] javaSize(Path root) throws IOException {
        long files = 0;
        long lines = 0;
        try (Stream<Path> walk = Files.walk(root)) {
            for (Path file : (Iterable<Path>) walk.filter(Files::isRegularFile)::iterator) {
                Path relative = root.relativize(file);
                boolean skipped = false;
                for (int i = 0; i < relative.getNameCount() - 1; i++) {
                    skipped |= SKIPPED_DIRECTORIES.contains(relative.getName(i).toString());
                }
                if (!skipped && Objects.requireNonNull(file.getFileName()).toString().endsWith(".java")) {
                    files++;
                    lines += lineBreaks(file);
                }
            }
        }
        return new long[] {files, lines};
    }

    /** The lines of a file by its line breaks, so a file that is not valid UTF-8 is counted too. */
    private static long lineBreaks(Path file) {
        try {
            String text = new String(Files.readAllBytes(file), StandardCharsets.ISO_8859_1);
            long breaks = text.chars().filter(c -> c == '\n').count();
            return text.isEmpty() || text.endsWith("\n") ? breaks : breaks + 1;
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    /** The report section for the measurements of one run of the task. */
    public static String render(List<Result> results) {
        StringBuilder out = new StringBuilder("## 5. Performans (NFR-01: ≤ 300 sn)\n\n");
        out.append("Ölçüm süreç içinde yapıldı (gerçek dosya sistemi; HTTP katmanı yok). İlk koşu soğuktur (sınıf yükleme, JIT), ")
                .append("diğerleri ısınmış süreyi gösterir; 100 sn'yi aşan bir koşudan sonra yeni koşu başlamaz. Projeler WSL'den `/mnt/c` ")
                .append("(Windows diski) üzerinden okundu; ext4'e göre dosya erişimi daha yavaş olabilir.\n\n");
        for (Result r : results) {
            out.append("### ").append(r.project()).append("\n\n");
            out.append("| Ölçüt | Değer |\n|---|---|\n");
            out.append("| Yol | ").append(r.wholeUseCase() ? "tam kullanım yolu: proje türü, eklenti, dedektörler, CBOM"
                    : "eklenti ve CBOM yazıcı doğrudan (kökte build dosyası yok, proje türü tespiti yok; D-203)").append(" |\n");
            out.append("| Java dosyası ve satırı | ").append(r.javaFiles()).append(" dosya, ").append(r.javaLines()).append(" satır |\n");
            out.append("| Taranan dosya (tümü) | ").append(r.filesScanned()).append(" |\n");
            out.append("| Bulgu | ").append(r.findings()).append(" |\n");
            for (int i = 0; i < r.runsMs().size(); i++) {
                out.append("| Koşu ").append(i + 1).append(i == 0 ? " (soğuk)" : "").append(" | ").append(r.runsMs().get(i)).append(" ms |\n");
            }
            out.append("| En yüksek heap | ").append(r.peakHeapMiB()).append(" MiB (JVM üst sınırı ").append(r.maxHeapMiB()).append(" MiB) |\n");
            out.append("| Makine | ").append(r.processors()).append(" işlemci, Java ").append(r.java()).append(" |\n");
            out.append(String.format(Locale.ROOT, "| Hedef (≤ %d ms) | %s |%n%n", TARGET_MS, r.withinTarget() ? "Karşılandı" : "Karşılanmadı"));
        }
        out.append("Yalnızca bu projeler ve bu makine için geçerlidir; başka projelerde süre dosya sayısına ve en büyük dosyaya göre değişir.\n");
        return out.toString();
    }
}
