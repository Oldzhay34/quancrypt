"""The mining tables of ml_outputs (P7.4, D-338g; ERD docs/data/ml_outputs-erd.md section 8).

One run per technique is kept (`mining_run`, keyed by the technique); a new run replaces it as a whole, its rows go by
CASCADE, and the history stays in MLflow. 3NF (BCNF). `project_archetype` and `anomaly` hold a project key and are
registered for the KVKK erasure by data-platform 0007; there is no foreign key to the warehouse, which dbt rebuilds.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

APP_ROLE = "warehouse_db_app"

TECHNIQUES = (
    ("KMEANS", "K-Means kümeleme (arketip)"),
    ("HDBSCAN", "HDBSCAN kümeleme (karşılaştırma)"),
    ("FP_GROWTH", "FP-Growth birliktelik kuralları"),
    ("ISOLATION_FOREST", "Isolation Forest anomali tespiti"),
)
TABLES = (
    "mining_run", "mining_run_parameter", "archetype", "project_archetype", "association_rule", "association_rule_item",
    "anomaly",
)  # fmt: skip
PROJECT_KEY = "'^[0-9a-f]{64}$'"


def _run_fk(table: str) -> str:
    return (
        f"CONSTRAINT fk_{table}_run FOREIGN KEY (technique) REFERENCES ml_outputs.mining_run (technique) "
        "ON DELETE CASCADE"
    )


STATEMENTS = (
    "CREATE TABLE ml_outputs.mining_technique (code varchar(32) NOT NULL, description varchar(200) NOT NULL, "
    "CONSTRAINT pk_mining_technique PRIMARY KEY (code))",
    "CREATE TABLE ml_outputs.mining_run ("
    "technique varchar(32) NOT NULL, mlflow_run_id varchar(32), run_at timestamptz NOT NULL, "
    "project_count integer NOT NULL, "
    "CONSTRAINT pk_mining_run PRIMARY KEY (technique), "
    "CONSTRAINT fk_mining_run_technique FOREIGN KEY (technique) "
    "REFERENCES ml_outputs.mining_technique (code) ON DELETE RESTRICT, "
    "CONSTRAINT ck_mining_run_mlflow CHECK (mlflow_run_id IS NULL OR mlflow_run_id ~ '^[0-9a-f]{32}$'), "
    "CONSTRAINT ck_mining_run_projects CHECK (project_count >= 0))",
    "CREATE TABLE ml_outputs.mining_run_parameter ("
    "technique varchar(32) NOT NULL, name varchar(64) NOT NULL, value varchar(128) NOT NULL, "
    "CONSTRAINT pk_mining_run_parameter PRIMARY KEY (technique, name), "
    f"{_run_fk('mining_run_parameter')}, "
    "CONSTRAINT ck_mining_run_parameter_name CHECK (name ~ '^[a-z0-9_]{1,64}$'))",
    "CREATE TABLE ml_outputs.archetype ("
    "technique varchar(32) NOT NULL, cluster_no smallint NOT NULL, name varchar(128) NOT NULL, "
    "rationale varchar(500) NOT NULL, "
    "CONSTRAINT pk_archetype PRIMARY KEY (technique, cluster_no), "
    "CONSTRAINT uq_archetype_name UNIQUE (technique, name), "
    f"{_run_fk('archetype')}, "
    "CONSTRAINT ck_archetype_cluster CHECK (cluster_no >= 1), "
    "CONSTRAINT ck_archetype_technique CHECK (technique IN ('KMEANS', 'HDBSCAN')))",
    "CREATE TABLE ml_outputs.project_archetype ("
    "technique varchar(32) NOT NULL, project_key char(64) NOT NULL, cluster_no smallint, "
    "CONSTRAINT pk_project_archetype PRIMARY KEY (technique, project_key), "
    f"{_run_fk('project_archetype')}, "
    "CONSTRAINT fk_project_archetype_cluster FOREIGN KEY (technique, cluster_no) "
    "REFERENCES ml_outputs.archetype (technique, cluster_no) ON DELETE CASCADE, "
    "CONSTRAINT ck_project_archetype_technique CHECK (technique IN ('KMEANS', 'HDBSCAN')), "
    # HDBSCAN leaves outlying projects in no cluster; K-Means assigns every project.
    "CONSTRAINT ck_project_archetype_noise CHECK (cluster_no IS NOT NULL OR technique = 'HDBSCAN'), "
    f"CONSTRAINT ck_project_archetype_key CHECK (project_key ~ {PROJECT_KEY}))",
    "CREATE INDEX ix_project_archetype_cluster ON ml_outputs.project_archetype (technique, cluster_no)",
    "CREATE INDEX ix_project_archetype_project_key ON ml_outputs.project_archetype (project_key)",
    "CREATE TABLE ml_outputs.association_rule ("
    "technique varchar(32) NOT NULL, rule_no integer NOT NULL, support double precision NOT NULL, "
    "confidence double precision NOT NULL, lift double precision NOT NULL, "
    "CONSTRAINT pk_association_rule PRIMARY KEY (technique, rule_no), "
    f"{_run_fk('association_rule')}, "
    "CONSTRAINT ck_association_rule_technique CHECK (technique = 'FP_GROWTH'), "
    "CONSTRAINT ck_association_rule_no CHECK (rule_no >= 1), "
    "CONSTRAINT ck_association_rule_support CHECK (support > 0 AND support <= 1), "
    "CONSTRAINT ck_association_rule_confidence CHECK (confidence > 0 AND confidence <= 1), "
    "CONSTRAINT ck_association_rule_lift CHECK (lift > 0 AND lift < 'Infinity'::double precision))",
    "CREATE TABLE ml_outputs.association_rule_item ("
    "technique varchar(32) NOT NULL, rule_no integer NOT NULL, item varchar(128) NOT NULL, side varchar(16) NOT NULL, "
    "CONSTRAINT pk_association_rule_item PRIMARY KEY (technique, rule_no, item), "
    "CONSTRAINT fk_association_rule_item_rule FOREIGN KEY (technique, rule_no) "
    "REFERENCES ml_outputs.association_rule (technique, rule_no) ON DELETE CASCADE, "
    "CONSTRAINT ck_association_rule_item_side CHECK (side IN ('ANTECEDENT', 'CONSEQUENT')), "
    "CONSTRAINT ck_association_rule_item_item CHECK (item ~ '^(lib|alg):[A-Za-z0-9_.-]{1,120}$'))",
    "CREATE TABLE ml_outputs.anomaly ("
    "technique varchar(32) NOT NULL, project_key char(64) NOT NULL, score double precision NOT NULL, "
    "is_flagged boolean NOT NULL, "
    "CONSTRAINT pk_anomaly PRIMARY KEY (technique, project_key), "
    f"{_run_fk('anomaly')}, "
    "CONSTRAINT ck_anomaly_technique CHECK (technique = 'ISOLATION_FOREST'), "
    "CONSTRAINT ck_anomaly_score CHECK (score > '-Infinity'::double precision "
    "AND score < 'Infinity'::double precision), "
    f"CONSTRAINT ck_anomaly_key CHECK (project_key ~ {PROJECT_KEY}))",
    "CREATE INDEX ix_anomaly_project_key ON ml_outputs.anomaly (project_key)",
    "INSERT INTO ml_outputs.mining_technique (code, description) VALUES "
    + ", ".join(f"('{code}', '{description}')" for code, description in TECHNIQUES),
    f"GRANT SELECT ON ml_outputs.mining_technique TO {APP_ROLE}",
    # A technique's run is replaced as a whole (delete + insert); nothing is updated in place.
    f"GRANT SELECT, INSERT, DELETE ON {', '.join(f'ml_outputs.{t}' for t in TABLES)} TO {APP_ROLE}",
)


def upgrade() -> None:
    connection = op.get_bind()
    for statement in STATEMENTS:
        connection.exec_driver_sql(statement)


def downgrade() -> None:
    raise NotImplementedError("migrations move forward only (acid-3nf-database section 4)")
