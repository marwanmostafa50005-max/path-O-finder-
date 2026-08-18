"""End-to-end analysis run: ingestion → extraction → detection → flags.

Initials-gated: every run starts with Repository.start_run(operator_initials)
(which refuses blank initials) and is fully audited. NEVER-DROP: every file
found this pass ends up parsed, quarantined, or recorded duplicate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from .config.loader import ConfigStore
from .db.repository import Repository
from .detection.flags import build_flag
from .detection.grace import GraceMatrix
from .extraction import coherence, hl7_tier1, normalize, pdf_tier2, pit
from .extraction.records import ExtractedResult, OrderInfo, ParsedMessage, Provenance
from .ingestion import quarantine as quarantine_mod
from .ingestion import sniffer, watcher
from .ingestion.adapters import get_adapter


@dataclass
class RunReport:
    run_id: int
    files_seen: int = 0
    messages_parsed: int = 0
    quarantined: int = 0
    duplicates: int = 0
    results_stored: int = 0
    flags_built: int = 0
    corrections_applied: int = 0
    notes: list[str] = field(default_factory=list)


class Pipeline:
    def __init__(self, repo: Repository, config: ConfigStore | None = None):
        self.repo = repo
        self.config = config or ConfigStore(repo)
        self.settings = self.config.get("settings")
        self.matrix = GraceMatrix.from_yaml(self.config.get_yaml("grace_matrix"))
        self.adapter = get_adapter(self.settings.get("source_adapter", "generic"))

    # -- public entry -----------------------------------------------------

    def run(self, operator_initials: str,
            watched_folder: Path | None = None) -> RunReport:
        """One initials-gated analysis run over the watched folder."""
        run_id = self.repo.start_run(operator_initials, {
            "closed_loop_mode": self.settings.get("closed_loop_mode"),
            "closed_loop_strictness": self.settings.get("closed_loop_strictness"),
            "source_adapter": self.adapter.name,
            "grace_matrix_version": self.matrix.version,
        })
        report = RunReport(run_id=run_id)

        folder = watched_folder or Path(self.settings.get("watched_folder") or "")
        if not folder or not folder.is_dir():
            report.notes.append("watched folder not configured or missing")
            self.repo.finish_run(run_id, 0, 0)
            return report

        files = watcher.scan_folder(folder, paths.inbox_dir(), self.repo,
                                    patterns=self.adapter.file_patterns())
        report.files_seen = len(files)

        for f in files:
            if f.duplicate:
                report.duplicates += 1
                continue
            self._process_file(f, report, operator_initials)

        self.repo.finish_run(run_id, report.files_seen, report.flags_built)
        return report

    # -- per-file ---------------------------------------------------------

    def _process_file(self, f: watcher.IngestedFile, report: RunReport,
                      initials: str) -> None:
        sr = f.sniff
        common = dict(source_adapter=self.adapter.name,
                      original_path=str(f.original_path), sha256=f.sha256,
                      raw=f.raw, quarantine_folder=paths.quarantine_dir(),
                      actor_initials=initials)

        if sr.file_type == sniffer.FileType.UNKNOWN:
            quarantine_mod.quarantine(self.repo, file_type="unknown",
                                      reason="; ".join(sr.notes) or "unrecognised file shape",
                                      **common)
            report.quarantined += 1
            return

        if sr.file_type == sniffer.FileType.HL7_BATCH and sr.truncated_batch:
            quarantine_mod.quarantine(self.repo, file_type="hl7_batch",
                                      reason="batch missing BTS/FTS trailer — possible truncation",
                                      **common)
            report.quarantined += 1
            return

        if sr.file_type == sniffer.FileType.HL7:
            try:
                parsed = hl7_tier1.parse_oru(sr.messages[0])
            except hl7_tier1.ParseFailure as e:
                quarantine_mod.quarantine(self.repo, file_type="hl7",
                                          reason=str(e), **common)
                report.quarantined += 1
                return
            self._store_message(parsed, sha256=f.sha256,
                                original_path=str(f.original_path),
                                raw=f.raw, report=report)
            return

        if sr.file_type == sniffer.FileType.HL7_BATCH:
            # A batch shares one file sha; each inner message is keyed by its
            # own content sha so per-message idempotency holds, and a file-
            # level marker row keeps watcher-level dedup working.
            failures: list[str] = []
            parsed_any = False
            for m_text in sr.messages:
                msg_sha = watcher.sha256_of(m_text.encode("utf-8"))
                try:
                    parsed = hl7_tier1.parse_oru(m_text)
                except hl7_tier1.ParseFailure as e:
                    failures.append(str(e))
                    continue
                if self.repo.message_seen(msg_sha, parsed.control_id):
                    report.duplicates += 1
                    continue
                self._store_message(parsed, sha256=msg_sha,
                                    original_path=str(f.original_path),
                                    raw=m_text.encode("utf-8"), report=report)
                parsed_any = True
            if failures:
                # Batch marker quarantined: unparsable remainder retained for review.
                quarantine_mod.quarantine(
                    self.repo, file_type="hl7_batch",
                    reason=f"{len(failures)} message(s) unparsable: " + "; ".join(failures),
                    **common)
                report.quarantined += 1
            else:
                self.repo.record_message(
                    source_adapter=self.adapter.name, original_path=str(f.original_path),
                    file_type="hl7_batch", sha256=f.sha256, status="parsed",
                    raw_blob=f.raw)
            if not parsed_any and not failures:
                report.notes.append(f"{f.original_path}: batch contained only duplicates")
            return

        if sr.file_type == sniffer.FileType.PIT:
            text = f.raw.decode("utf-8", errors="replace")
            results, _lines = pit.parse_pit(text, source_note=f.original_path.name)
            if not results:
                quarantine_mod.quarantine(self.repo, file_type="pit",
                                          reason="PIT report contained no confidently readable result line",
                                          **common)
                report.quarantined += 1
                return
            msg = ParsedMessage(control_id=None, patient=None,
                                orders=[OrderInfo(obr_set_id="pit", results=results)])
            self._store_message(msg, sha256=f.sha256,
                                original_path=str(f.original_path),
                                raw=f.raw, report=report, file_type="pit")
            return

        if sr.file_type == sniffer.FileType.PDF:
            self._process_pdf_bytes(f.raw, f, report, initials, standalone=True)
            return

    def _process_pdf_bytes(self, pdf_bytes: bytes, f: watcher.IngestedFile,
                           report: RunReport, initials: str,
                           standalone: bool) -> None:
        gate = float(self.settings.get("ocr_confidence_gate", 80))
        ext = pdf_tier2.extract_from_pdf(pdf_bytes, ocr_confidence_gate=gate)

        results = list(ext.results)
        # OCR abstentions become explicit check-yourself records — never dropped.
        for reason in ext.abstentions:
            r = ExtractedResult(analyte_raw="(unreadable report line)",
                                extraction_tier=2, confidence=0.0,
                                provenance=Provenance(tier=2, engine="ocr-gate"))
            r.abstain(reason)
            results.append(r)

        if not results:
            if standalone:
                quarantine_mod.quarantine(
                    self.repo, file_type="pdf",
                    reason="no readable result lines (and no OCR-gated candidates)",
                    source_adapter=self.adapter.name, original_path=str(f.original_path),
                    sha256=f.sha256, raw=pdf_bytes,
                    quarantine_folder=paths.quarantine_dir(), actor_initials=initials)
                report.quarantined += 1
            return

        msg = ParsedMessage(control_id=None, patient=None,
                            orders=[OrderInfo(obr_set_id="pdf", results=results)])
        self._store_message(msg, sha256=f.sha256,
                            original_path=str(f.original_path),
                            raw=pdf_bytes, report=report, file_type="pdf")

    # -- persistence ------------------------------------------------------

    def _store_message(self, parsed: ParsedMessage, *, sha256: str,
                       original_path: str, raw: bytes,
                       report: RunReport, file_type: str = "hl7") -> None:
        message_id = self.repo.record_message(
            source_adapter=self.adapter.name, original_path=original_path,
            file_type=file_type, sha256=sha256, status="parsed",
            raw_blob=raw, control_id=parsed.control_id)
        report.messages_parsed += 1

        patient_id = None
        if parsed.patient:
            p = parsed.patient
            patient_id = self.repo.upsert_patient(
                p.source_key, p.family_name, p.given_names, p.dob, p.sex)

        aliases = self.repo.aliases()
        for order in parsed.orders:
            order_id = self.repo.insert_order(
                message_id,
                obr_set_id=order.obr_set_id,
                filler_order_number=order.filler_order_number,
                ordering_provider=order.ordering_provider,
                order_status=order.order_status,
                collected_at=order.collected_at,
                reported_at=order.reported_at,
                panel_code=order.panel_code,
                panel_name=order.panel_name)

            # Embedded payloads: PIT text and ED PDFs ride along inside OBX.
            for pit_text in order.embedded_pit:
                pit_results, _ = pit.parse_pit(pit_text, source_note="embedded-pit")
                order.results.extend(pit_results)
            for doc in order.embedded_documents:
                if doc.startswith(b"%PDF-"):
                    gate = float(self.settings.get("ocr_confidence_gate", 80))
                    ext = pdf_tier2.extract_from_pdf(doc, ocr_confidence_gate=gate)
                    order.results.extend(ext.results)
                    for reason in ext.abstentions:
                        r = ExtractedResult(analyte_raw="(unreadable embedded report line)",
                                            extraction_tier=2, confidence=0.0,
                                            provenance=Provenance(tier=2, engine="ocr-gate"))
                        r.abstain(reason)
                        order.results.append(r)

            for res in order.results:
                normalize.normalize_result(res, local_aliases=aliases)
                coherence.run_coherence(res)

                result_id = self.repo.insert_result(order_id, patient_id, res.db_record())
                report.results_stored += 1

                # OBX-11=C: supersede the prior value, keep original in audit.
                if (res.obx_result_status or "").upper() == "C":
                    prior = self.repo.find_result_for_correction(
                        order.filler_order_number, res.obx_identifier, res.obx_sub_id,
                        exclude_result_id=result_id)
                    if prior:
                        self.repo.supersede_result(prior, result_id)
                        report.corrections_applied += 1
                else:
                    # Out-of-order feed: if a correction for this observation
                    # is already on file, this older P/F must not resurface.
                    existing_c = self.repo.find_result_for_correction(
                        order.filler_order_number, res.obx_identifier, res.obx_sub_id,
                        exclude_result_id=result_id, only_status="C")
                    if existing_c:
                        self.repo.supersede_result(result_id, existing_c)
                        report.corrections_applied += 1

                flag = build_flag(res, self.matrix, order.reported_at)
                if flag:
                    self.repo.create_flag(result_id, flag["severity_tier"],
                                          flag["flag_reason"], flag["is_check_yourself"],
                                          flag["grace_deadline"])
                    report.flags_built += 1
