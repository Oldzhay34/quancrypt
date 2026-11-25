"""ml_outputs codes of Model B (P7.3, D-333f): the calibrated linear SVM, the approved scope data set as a label source,
the validation scope and the scope classifier's metrics and slices. Lookup rows only; no table changes."""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

ROWS = {
    "algorithm": (("LINEAR_SVM", "Doğrusal SVM (sigmoid kalibrasyonlu)"),),
    "label_source": (("SCOPE_SET", "Onaylı kapsam veri seti (D-326)"),),
    "metric_scope": (("VALIDATION", "Doğrulama kümesi (eşik ve bant burada seçilir)"),),
    "metric": (
        ("OUT_OF_SCOPE_RECALL", "Kapsam dışı isteklerin reddedilen payı"),
        ("FALSE_REJECT_RATE", "Kapsam içi isteklerin reddedilen payı"),
        ("UNSURE_RATE", "3. halkaya bırakılan isteklerin payı"),
        ("THRESHOLD", "Kapsam dışı olasılık eşiği"),
        ("UNSURE_LOW", "UNSURE bandının alt sınırı"),
        ("UNSURE_HIGH", "UNSURE bandının üst sınırı"),
        ("ROC_AUC", "ROC eğrisi altındaki alan"),
    ),
    "metric_label": (
        ("TR", "Türkçe istekler"), ("EN", "İngilizce istekler"), ("JAILBREAK", "Jailbreak istekleri"),
        ("BOUNDARY", "Sınır durumu istekleri"),
    ),
}  # fmt: skip


def upgrade() -> None:
    connection = op.get_bind()
    for table, rows in ROWS.items():
        connection.exec_driver_sql(
            f"INSERT INTO ml_outputs.{table} (code, description) VALUES "
            + ", ".join(f"('{code}', '{description}')" for code, description in rows)
        )


def downgrade() -> None:
    raise NotImplementedError("migrations move forward only (acid-3nf-database section 4)")
