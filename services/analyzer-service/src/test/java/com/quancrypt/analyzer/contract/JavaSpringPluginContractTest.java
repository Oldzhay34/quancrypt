package com.quancrypt.analyzer.contract;

import com.quancrypt.analyzer.domain.model.AnalysisRoot;
import com.quancrypt.analyzer.domain.model.CanonicalNames;
import com.quancrypt.analyzer.fake.InMemorySourceTreeReader;
import com.quancrypt.analyzer.infrastructure.dictionary.CanonicalDictionaryLoader;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaSpringPlugins;
import com.quancrypt.analyzer.port.outbound.LanguagePlugin;
import com.quancrypt.analyzer.port.outbound.SourceTree;

/** The real Java / Spring Boot plugin passes the same contract as the test double. */
class JavaSpringPluginContractTest extends LanguagePluginContract {

    @Override
    protected LanguagePlugin plugin() {
        return JavaSpringPlugins.standard(new CanonicalNames(new CanonicalDictionaryLoader().loadFromClasspath()));
    }

    @Override
    protected SourceTree tree() {
        return new InMemorySourceTreeReader()
                .file("/workspace/project", "pom.xml", "<project><properties><java.version>21</java.version></properties></project>")
                .file("/workspace/project", "src/main/java/A.java", "import javax.crypto.Cipher;\nclass A {\n    void a() throws Exception {\n"
                        + "        Cipher.getInstance(\"RSA/ECB/PKCS1Padding\");\n    }\n}\n")
                .file("/workspace/project", "src/main/resources/application.yml", "server:\n  ssl:\n    bundle: web\n")
                .open(new AnalysisRoot("/workspace/project"));
    }
}

