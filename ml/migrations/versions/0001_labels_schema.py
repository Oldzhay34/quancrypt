"""The labels schema of warehouse_db (P7.1, D-25, D-322, ERD docs/data/labels-erd.md).

Gold labels of Model A: `labeled_finding` is a warehouse finding that was ever sampled, with its project key; a batch
is a stratified sample of them (`label_batch_item`, and whether the second labeller labels the record too);
`gold_label` holds the label of each labeller, `label_resolution` the user's resolution of a disagreement. 3NF (BCNF,
D-324a): the project key depends on the finding alone and lives in its own table; the size of a batch is counted from
its items, not stored.

There is no foreign key to prep or the warehouse (D-322g): prep is rewritten by every preprocessing run (with the same
uuid5 ids) and the warehouse by every dbt build; a key would either erase the labels or block both pipelines. The
project key is stored for the KVKK erasure (data-platform registers `labels.labeled_finding`; its batch items, labels
and resolutions go with it by CASCADE). The application role reads and writes what the command line needs (D-324c),
warehouse_reader sees nothing (D-24).

Revision ID: 0001
Revises:
"""

from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

APP_ROLE = "warehouse_db_app"

RISK_CLASSES = (
    ("CRITICAL", "Bugün kırılabilen zayıf kripto, test dışı kodda (crypto-domain kuralı 1)", 1),
    ("HIGH", "Servisler arası yolda veya saha cihazında anahtar kurulumu (kural 2)", 2),
    ("MEDIUM", "Ağ yolunda olmayan anahtar kurulumu veya uzun ömürlü imza (kural 3)", 3),
    ("LOW", "Kısa ömürlü token, sertifika ve kimlik doğrulaması (kural 4)", 4),
)
LABELER_ROLES = (
    ("FIRST", "Tüm partiyi etiketleyen kişi"),
    ("SECOND", "Yalnız çift etiketleme için işaretli kayıtları etiketleyen kişi"),
)

STATEMENTS = (
    "CREATE SCHEMA labels",
    "CREATE TABLE labels.risk_class ("
    "code varchar(16) NOT NULL, description varchar(200) NOT NULL, sort_order smallint NOT NULL, "
    "CONSTRAINT pk_risk_class PRIMARY KEY (code), CONSTRAINT uq_risk_class_sort_order UNIQUE (sort_order))",
    "CREATE TABLE labels.labeler_role ("
    "code varchar(16) NOT NULL, description varchar(200) NOT NULL, CONSTRAINT pk_labeler_role PRIMARY KEY (code))",
    "CREATE TABLE labels.labeler ("
    "id uuid NOT NULL, name varchar(64) NOT NULL, "
    "CONSTRAINT pk_labeler PRIMARY KEY (id), CONSTRAINT uq_labeler_name UNIQUE (name), "
    "CONSTRAINT ck_labeler_name CHECK (btrim(name) = name AND name <> ''))",
    "CREATE TABLE labels.label_batch ("
    "id uuid NOT NULL, name varchar(64) NOT NULL, created_at timestamptz NOT NULL, seed integer NOT NULL, "
    "CONSTRAINT pk_label_batch PRIMARY KEY (id), CONSTRAINT uq_label_batch_name UNIQUE (name), "
    "CONSTRAINT ck_label_batch_name CHECK (name ~ '^[a-z0-9_]{1,64}$'))",
    "CREATE TABLE labels.labeled_finding ("
    "finding_id uuid NOT NULL, project_key char(64) NOT NULL, "
    "CONSTRAINT pk_labeled_finding PRIMARY KEY (finding_id), "
    "CONSTRAINT ck_labeled_finding_project_key CHECK (project_key ~ '^[0-9a-f]{64}$'))",
    "CREATE INDEX ix_labeled_finding_project_key ON labels.labeled_finding (project_key)",
    "CREATE TABLE labels.label_batch_item ("
    "batch_id uuid NOT NULL, finding_id uuid NOT NULL, double_label boolean NOT NULL, "
    "CONSTRAINT pk_label_batch_item PRIMARY KEY (batch_id, finding_id), "
    "CONSTRAINT fk_label_batch_item_batch FOREIGN KEY (batch_id) REFERENCES labels.label_batch (id) ON DELETE CASCADE, "
    "CONSTRAINT fk_label_batch_item_finding FOREIGN KEY (finding_id) "
    "REFERENCES labels.labeled_finding (finding_id) ON DELETE CASCADE)",
    "CREATE INDEX ix_label_batch_item_finding ON labels.label_batch_item (finding_id)",
    "CREATE TABLE labels.gold_label ("
    "batch_id uuid NOT NULL, finding_id uuid NOT NULL, labeler_role varchar(16) NOT NULL, labeler_id uuid NOT NULL, "
    "risk_class varchar(16) NOT NULL, notes varchar(500), labeled_at timestamptz NOT NULL, "
    "CONSTRAINT pk_gold_label PRIMARY KEY (batch_id, finding_id, labeler_role), "
    "CONSTRAINT fk_gold_label_item FOREIGN KEY (batch_id, finding_id) "
    "REFERENCES labels.label_batch_item (batch_id, finding_id) ON DELETE CASCADE, "
    "CONSTRAINT fk_gold_label_role FOREIGN KEY (labeler_role) REFERENCES labels.labeler_role (code) ON DELETE RESTRICT, "
    "CONSTRAINT fk_gold_label_labeler FOREIGN KEY (labeler_id) REFERENCES labels.labeler (id) ON DELETE RESTRICT, "
    "CONSTRAINT fk_gold_label_risk_class FOREIGN KEY (risk_class) REFERENCES labels.risk_class (code) ON DELETE RESTRICT, "
    "CONSTRAINT ck_gold_label_notes CHECK (notes IS NULL OR (btrim(notes) = notes AND notes <> '')))",
    "CREATE INDEX ix_gold_label_labeler ON labels.gold_label (labeler_id)",
    "CREATE TABLE labels.label_resolution ("
    "batch_id uuid NOT NULL, finding_id uuid NOT NULL, risk_class varchar(16) NOT NULL, resolved_by uuid NOT NULL, "
    "notes varchar(500), resolved_at timestamptz NOT NULL, "
    "CONSTRAINT pk_label_resolution PRIMARY KEY (batch_id, finding_id), "
    "CONSTRAINT fk_label_resolution_item FOREIGN KEY (batch_id, finding_id) "
    "REFERENCES labels.label_batch_item (batch_id, finding_id) ON DELETE CASCADE, "
    "CONSTRAINT fk_label_resolution_risk_class FOREIGN KEY (risk_class) "
    "REFERENCES labels.risk_class (code) ON DELETE RESTRICT, "
    "CONSTRAINT fk_label_resolution_labeler FOREIGN KEY (resolved_by) REFERENCES labels.labeler (id) ON DELETE RESTRICT, "
    "CONSTRAINT ck_label_resolution_notes CHECK (notes IS NULL OR (btrim(notes) = notes AND notes <> '')))",
    "CREATE INDEX ix_label_resolution_labeler ON labels.label_resolution (resolved_by)",
    "INSERT INTO labels.risk_class (code, description, sort_order) VALUES "
    + ", ".join(f"('{c}', '{d}', {o})" for c, d, o in RISK_CLASSES),
    "INSERT INTO labels.labeler_role (code, description) VALUES "
    + ", ".join(f"('{c}', '{d}')" for c, d in LABELER_ROLES),
    f"GRANT USAGE ON SCHEMA labels TO {APP_ROLE}",
    f"GRANT SELECT ON labels.risk_class, labels.labeler_role TO {APP_ROLE}",
    f"GRANT SELECT, INSERT ON labels.labeler TO {APP_ROLE}",
    # Batches and items are written once (D-324c): the application never deletes them. A labelled finding is deleted only
    # by the KVKK erasure (data-platform, the same role); its items, labels and resolutions follow by CASCADE.
    f"GRANT SELECT, INSERT ON labels.label_batch, labels.label_batch_item TO {APP_ROLE}",
    f"GRANT SELECT, INSERT, DELETE ON labels.labeled_finding, labels.gold_label, labels.label_resolution TO {APP_ROLE}",
    # Alembic's table of this chain is created by the migrator in `public`, where the init script's default privileges
    # would give the application role DML on it (data-platform 0001 precedent): the application never changes the version.
    f"REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON public.ml_alembic_version FROM {APP_ROLE}",
)


def upgrade() -> None:
    connection = op.get_bind()
    for statement in STATEMENTS:
        connection.exec_driver_sql(statement)


def downgrade() -> None:
    raise NotImplementedError("migrations move forward only (acid-3nf-database section 4)")
