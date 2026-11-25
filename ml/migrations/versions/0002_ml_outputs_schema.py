"""The ml_outputs schema of warehouse_db (P7.2, D-327d, D-328; ERD docs/data/ml_outputs-erd.md).

Model A's outputs: a `model_version` (the trained risk model and its two baselines), the version `published_model` the
warehouse marts read, the scored findings (`scored_finding`: finding and project key, the 2NF lesson of D-324a),
predictions, their three strongest SHAP attributions, and the evaluation metrics. 3NF (BCNF). A model version is replaced
as a whole (its rows go by CASCADE) when it is trained again. There is no foreign key to the warehouse (dbt rebuilds it)
or to labels; data-platform registers `ml_outputs.scored_finding` for the KVKK erasure (its predictions and explanations
go with it by CASCADE). P7.4 adds the mining tables.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

APP_ROLE = "warehouse_db_app"

LOOKUPS = {
    "algorithm": (
        ("LOGISTIC_REGRESSION", "Lojistik regresyon"), ("RANDOM_FOREST", "Random Forest"), ("XGBOOST", "XGBoost"),
        ("RULE_BASELINE", "crypto-domain kural tablosu (gümüş etiket)"), ("LLM_ZERO_SHOT", "Yerel LLM sıfır-atış"),
    ),
    "label_source": (("GOLD", "Kullanıcının altın etiketi"), ("SILVER", "Kural tablosu (gümüş etiket)")),
    "metric_scope": (
        ("CV_FOLD", "Bir doğrulama katı"), ("CV_MEAN", "Doğrulama katlarının ortalaması"),
        ("CV_STD", "Doğrulama katlarının standart sapması"), ("TEST", "Hiç görülmemiş test projeleri"),
    ),
    "metric": (
        ("MACRO_F1", "Macro-F1"), ("MACRO_F1_CI_LOW", "Macro-F1 yüzde 95 bootstrap alt sınırı"),
        ("MACRO_F1_CI_HIGH", "Macro-F1 yüzde 95 bootstrap üst sınırı"), ("ACCURACY", "Doğruluk"),
        ("INVALID_ANSWERS", "Dört sınıftan biri olmayan yanıt sayısı"), ("PRECISION", "Precision"),
        ("RECALL", "Recall"), ("F1", "F1"), ("SUPPORT", "Destek (gerçek kayıt sayısı)"),
        ("SECONDS_PER_FINDING", "Bulgu başına süre (saniye)"), ("TOKENS_PER_FINDING", "Bulgu başına token"),
        ("RUN_AGREEMENT", "İki koşunun aynı yanıt payı"),
    ),
    "metric_label": (
        ("ALL", "Tüm sınıflar"), ("CRITICAL", "CRITICAL"), ("HIGH", "HIGH"), ("MEDIUM", "MEDIUM"), ("LOW", "LOW"),
    ),
}  # fmt: skip
RISK_CLASSES = (("CRITICAL", 1), ("HIGH", 2), ("MEDIUM", 3), ("LOW", 4))
NAME = r"^[a-z0-9_]{1,64}$"
VERSION = r"^[A-Za-z0-9._:-]{1,64}$"


def _lookup(table: str) -> str:
    return (
        f"CREATE TABLE ml_outputs.{table} (code varchar(32) NOT NULL, description varchar(200) NOT NULL, "
        f"CONSTRAINT pk_{table} PRIMARY KEY (code))"
    )


STATEMENTS = (
    "CREATE SCHEMA ml_outputs",
    *(_lookup(table) for table in LOOKUPS),
    "CREATE TABLE ml_outputs.risk_class (code varchar(16) NOT NULL, sort_order smallint NOT NULL, "
    "CONSTRAINT pk_risk_class PRIMARY KEY (code), CONSTRAINT uq_risk_class_sort_order UNIQUE (sort_order))",
    "CREATE TABLE ml_outputs.model_version ("
    "id uuid NOT NULL, model_name varchar(64) NOT NULL, version varchar(64) NOT NULL, algorithm varchar(32) NOT NULL, "
    "label_source varchar(32) NOT NULL, mlflow_run_id varchar(32), trained_at timestamptz NOT NULL, "
    "CONSTRAINT pk_model_version PRIMARY KEY (id), "
    "CONSTRAINT uq_model_version_name_version UNIQUE (model_name, version), "
    "CONSTRAINT uq_model_version_name_id UNIQUE (model_name, id), "
    "CONSTRAINT fk_model_version_algorithm FOREIGN KEY (algorithm) REFERENCES ml_outputs.algorithm (code) ON DELETE RESTRICT, "
    "CONSTRAINT fk_model_version_label_source FOREIGN KEY (label_source) "
    "REFERENCES ml_outputs.label_source (code) ON DELETE RESTRICT, "
    f"CONSTRAINT ck_model_version_name CHECK (model_name ~ '{NAME}'), "
    f"CONSTRAINT ck_model_version_version CHECK (version ~ '{VERSION}'), "
    "CONSTRAINT ck_model_version_run CHECK (mlflow_run_id IS NULL OR mlflow_run_id ~ '^[0-9a-f]{32}$'))",
    "CREATE TABLE ml_outputs.published_model ("
    "model_name varchar(64) NOT NULL, model_version_id uuid NOT NULL, published_at timestamptz NOT NULL, "
    "CONSTRAINT pk_published_model PRIMARY KEY (model_name), "
    "CONSTRAINT uq_published_model_version UNIQUE (model_version_id), "
    "CONSTRAINT fk_published_model_version FOREIGN KEY (model_name, model_version_id) "
    "REFERENCES ml_outputs.model_version (model_name, id) ON DELETE CASCADE)",
    "CREATE TABLE ml_outputs.scored_finding ("
    "finding_id uuid NOT NULL, project_key char(64) NOT NULL, "
    "CONSTRAINT pk_scored_finding PRIMARY KEY (finding_id), "
    "CONSTRAINT ck_scored_finding_project_key CHECK (project_key ~ '^[0-9a-f]{64}$'))",
    "CREATE INDEX ix_scored_finding_project_key ON ml_outputs.scored_finding (project_key)",
    "CREATE TABLE ml_outputs.risk_prediction ("
    "model_version_id uuid NOT NULL, finding_id uuid NOT NULL, risk_class varchar(16) NOT NULL, "
    "risk_score numeric(5,4) NOT NULL, "
    "CONSTRAINT pk_risk_prediction PRIMARY KEY (model_version_id, finding_id), "
    "CONSTRAINT fk_risk_prediction_version FOREIGN KEY (model_version_id) "
    "REFERENCES ml_outputs.model_version (id) ON DELETE CASCADE, "
    "CONSTRAINT fk_risk_prediction_finding FOREIGN KEY (finding_id) "
    "REFERENCES ml_outputs.scored_finding (finding_id) ON DELETE CASCADE, "
    "CONSTRAINT fk_risk_prediction_class FOREIGN KEY (risk_class) REFERENCES ml_outputs.risk_class (code) ON DELETE RESTRICT, "
    "CONSTRAINT ck_risk_prediction_score CHECK (risk_score BETWEEN 0 AND 1))",
    "CREATE INDEX ix_risk_prediction_finding ON ml_outputs.risk_prediction (finding_id)",
    "CREATE TABLE ml_outputs.risk_explanation ("
    "model_version_id uuid NOT NULL, finding_id uuid NOT NULL, rank smallint NOT NULL, feature varchar(128) NOT NULL, "
    "shap_value double precision NOT NULL, "
    "CONSTRAINT pk_risk_explanation PRIMARY KEY (model_version_id, finding_id, rank), "
    "CONSTRAINT uq_risk_explanation_feature UNIQUE (model_version_id, finding_id, feature), "
    "CONSTRAINT fk_risk_explanation_prediction FOREIGN KEY (model_version_id, finding_id) "
    "REFERENCES ml_outputs.risk_prediction (model_version_id, finding_id) ON DELETE CASCADE, "
    "CONSTRAINT ck_risk_explanation_rank CHECK (rank BETWEEN 1 AND 3), "
    "CONSTRAINT ck_risk_explanation_feature CHECK (feature ~ '^[A-Za-z0-9_.:~-]{1,128}$'))",
    "CREATE TABLE ml_outputs.model_metric ("
    "model_version_id uuid NOT NULL, scope varchar(32) NOT NULL, fold smallint NOT NULL, metric varchar(32) NOT NULL, "
    "label varchar(32) NOT NULL, value double precision NOT NULL, "
    "CONSTRAINT pk_model_metric PRIMARY KEY (model_version_id, scope, fold, metric, label), "
    "CONSTRAINT fk_model_metric_version FOREIGN KEY (model_version_id) "
    "REFERENCES ml_outputs.model_version (id) ON DELETE CASCADE, "
    "CONSTRAINT fk_model_metric_scope FOREIGN KEY (scope) REFERENCES ml_outputs.metric_scope (code) ON DELETE RESTRICT, "
    "CONSTRAINT fk_model_metric_metric FOREIGN KEY (metric) REFERENCES ml_outputs.metric (code) ON DELETE RESTRICT, "
    "CONSTRAINT fk_model_metric_label FOREIGN KEY (label) REFERENCES ml_outputs.metric_label (code) ON DELETE RESTRICT, "
    "CONSTRAINT ck_model_metric_fold CHECK (fold >= 0 AND ((scope = 'CV_FOLD') = (fold > 0))))",
    *(
        f"INSERT INTO ml_outputs.{table} (code, description) VALUES "
        + ", ".join(f"('{code}', '{description}')" for code, description in rows)
        for table, rows in LOOKUPS.items()
    ),
    "INSERT INTO ml_outputs.risk_class (code, sort_order) VALUES "
    + ", ".join(f"('{c}', {o})" for c, o in RISK_CLASSES),
    f"GRANT USAGE ON SCHEMA ml_outputs TO {APP_ROLE}",
    f"GRANT SELECT ON {', '.join(f'ml_outputs.{t}' for t in (*LOOKUPS, 'risk_class'))} TO {APP_ROLE}",
    # A model version is replaced as a whole (delete + insert); nothing is updated in place.
    f"GRANT SELECT, INSERT, DELETE ON ml_outputs.model_version, ml_outputs.published_model, ml_outputs.scored_finding, "
    f"ml_outputs.risk_prediction, ml_outputs.risk_explanation, ml_outputs.model_metric TO {APP_ROLE}",
)


def upgrade() -> None:
    connection = op.get_bind()
    for statement in STATEMENTS:
        connection.exec_driver_sql(statement)


def downgrade() -> None:
    raise NotImplementedError("migrations move forward only (acid-3nf-database section 4)")
