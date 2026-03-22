"""Tests for normalizers."""

import pytest

from pipeline.normalizers.llm import LLMNormalizer, RuleBasedNormalizer
from pipeline.schemas.blocks import TableBlock, TextBlock
from pipeline.schemas.canonical import CanonicalDocument


class TestRuleBasedNormalizer:
    def setup_method(self):
        self.normalizer = RuleBasedNormalizer()

    def _make_doc(self, content: str) -> CanonicalDocument:
        return CanonicalDocument(
            source_system="test",
            source_uri="test://1",
            content_blocks=[TextBlock(content=content)],
        )

    def test_detects_abbreviations(self):
        doc = self._make_doc("The NPL ratio for CASA accounts is tracked daily.")
        doc = self.normalizer.normalize(doc)
        assert "abbreviations" in doc.metadata
        assert "NPL" in doc.metadata["abbreviations"]
        assert "CASA" in doc.metadata["abbreviations"]

    def test_detects_vietnamese(self):
        doc = self._make_doc("Dữ liệu được lưu trữ trong các bảng của hệ thống ngân hàng.")
        doc = self.normalizer.normalize(doc)
        assert doc.metadata.get("language") in ("vi", "mixed")

    def test_detects_english(self):
        doc = self._make_doc("The system processes banking transactions daily.")
        doc = self.normalizer.normalize(doc)
        assert doc.metadata.get("language") == "en"

    def test_no_abbreviations_for_unrelated_text(self):
        doc = self._make_doc("The weather is nice today.")
        doc = self.normalizer.normalize(doc)
        assert "abbreviations" not in doc.metadata


class TestLLMStructuredContent:
    """Test _inject_structured_blocks without calling the LLM."""

    def test_inject_overview(self):
        doc = CanonicalDocument(source_system="test", source_uri="test://1", title="Test")
        structured = {"overview": "This report covers FX transactions."}
        LLMNormalizer._inject_structured_blocks(doc, structured)
        texts = [b.content for b in doc.content_blocks if isinstance(b, TextBlock)]
        assert any("[Overview]" in t for t in texts)

    def test_inject_business_rules(self):
        doc = CanonicalDocument(source_system="test", source_uri="test://1", title="Test")
        structured = {"business_rules": ["Filter currency != SJC", "threshold >= 5M USD"]}
        LLMNormalizer._inject_structured_blocks(doc, structured)
        texts = [b.content for b in doc.content_blocks if isinstance(b, TextBlock)]
        assert any("Business Rules" in t and "SJC" in t for t in texts)

    def test_inject_field_mapping_as_table(self):
        doc = CanonicalDocument(source_system="test", source_uri="test://1", title="Test")
        structured = {
            "field_mapping": [
                {"field": "sym_run_date", "type": "date", "source": "p_date", "description": "Run date"},
                {"field": "kyhieu", "type": "string", "source": "'TOANHANG'", "description": "Code"},
            ]
        }
        LLMNormalizer._inject_structured_blocks(doc, structured)
        tables = [b for b in doc.content_blocks if isinstance(b, TableBlock)]
        assert len(tables) == 1
        assert tables[0].headers == ["field", "type", "source", "description"]
        assert len(tables[0].rows) == 2

    def test_inject_data_sources(self):
        doc = CanonicalDocument(source_system="test", source_uri="test://1", title="Test")
        structured = {
            "data_sources": [
                {"name": "ft_fx_master", "purpose": "FX transaction master data"},
            ]
        }
        LLMNormalizer._inject_structured_blocks(doc, structured)
        texts = [b.content for b in doc.content_blocks if isinstance(b, TextBlock)]
        assert any("ft_fx_master" in t for t in texts)

    def test_inject_definitions(self):
        doc = CanonicalDocument(source_system="test", source_uri="test://1", title="Test")
        structured = {"definitions": {"NPL": "Non-Performing Loan", "CASA": "Current Account"}}
        LLMNormalizer._inject_structured_blocks(doc, structured)
        texts = [b.content for b in doc.content_blocks if isinstance(b, TextBlock)]
        assert any("Definitions" in t and "NPL" in t for t in texts)

    def test_inject_empty_structured_is_noop(self):
        doc = CanonicalDocument(source_system="test", source_uri="test://1", title="Test")
        initial_count = len(doc.content_blocks)
        LLMNormalizer._inject_structured_blocks(doc, {})
        assert len(doc.content_blocks) == initial_count

    # ── New multi-domain sections ──

    def test_inject_key_concepts(self):
        doc = CanonicalDocument(source_system="test", source_uri="test://1", title="Test")
        structured = {"key_concepts": ["Credit scoring", "NPL classification", "Risk appetite"]}
        LLMNormalizer._inject_structured_blocks(doc, structured)
        texts = [b.content for b in doc.content_blocks if isinstance(b, TextBlock)]
        assert any("Key Concepts" in t and "Credit scoring" in t for t in texts)

    def test_inject_relationships(self):
        doc = CanonicalDocument(source_system="test", source_uri="test://1", title="Test")
        structured = {
            "relationships": [
                {"source": "ft_fx_master", "relation": "FEEDS", "target": "rpt_fx_daily"},
            ]
        }
        LLMNormalizer._inject_structured_blocks(doc, structured)
        texts = [b.content for b in doc.content_blocks if isinstance(b, TextBlock)]
        assert any("ft_fx_master" in t and "FEEDS" in t and "rpt_fx_daily" in t for t in texts)

    def test_inject_stakeholders(self):
        doc = CanonicalDocument(source_system="test", source_uri="test://1", title="Test")
        structured = {
            "stakeholders": [{"name": "Risk Team", "role": "Owner"}]
        }
        LLMNormalizer._inject_structured_blocks(doc, structured)
        texts = [b.content for b in doc.content_blocks if isinstance(b, TextBlock)]
        assert any("Risk Team" in t and "Owner" in t for t in texts)

    def test_inject_requirements(self):
        doc = CanonicalDocument(source_system="test", source_uri="test://1", title="Test")
        structured = {"requirements": ["Must report NPL within 24h", "All PII encrypted at rest"]}
        LLMNormalizer._inject_structured_blocks(doc, structured)
        texts = [b.content for b in doc.content_blocks if isinstance(b, TextBlock)]
        assert any("Requirements" in t and "NPL" in t for t in texts)

    def test_inject_workflow_steps(self):
        doc = CanonicalDocument(source_system="test", source_uri="test://1", title="Test")
        structured = {
            "workflow_steps": [
                {"step": 1, "action": "Extract data", "actor": "ETL", "output": "raw table"},
                {"step": 2, "action": "Validate", "actor": "QA"},
            ]
        }
        LLMNormalizer._inject_structured_blocks(doc, structured)
        texts = [b.content for b in doc.content_blocks if isinstance(b, TextBlock)]
        assert any("Workflow Steps" in t and "Extract data" in t for t in texts)

    def test_inject_features(self):
        doc = CanonicalDocument(source_system="test", source_uri="test://1", title="Test")
        structured = {
            "features": [{"name": "Auto-reconcile", "description": "Matches transactions automatically"}]
        }
        LLMNormalizer._inject_structured_blocks(doc, structured)
        texts = [b.content for b in doc.content_blocks if isinstance(b, TextBlock)]
        assert any("Auto-reconcile" in t for t in texts)

    def test_inject_decision_points(self):
        doc = CanonicalDocument(source_system="test", source_uri="test://1", title="Test")
        structured = {"decision_points": ["If amount > 500M VND → escalate to L2 approval"]}
        LLMNormalizer._inject_structured_blocks(doc, structured)
        texts = [b.content for b in doc.content_blocks if isinstance(b, TextBlock)]
        assert any("Decision Points" in t and "escalate" in t for t in texts)

    def test_inject_references(self):
        doc = CanonicalDocument(source_system="test", source_uri="test://1", title="Test")
        structured = {
            "references": [{"name": "SBV Circular 02", "type": "document", "context": "NPL classification"}]
        }
        LLMNormalizer._inject_structured_blocks(doc, structured)
        texts = [b.content for b in doc.content_blocks if isinstance(b, TextBlock)]
        assert any("SBV Circular 02" in t for t in texts)

    def test_inject_mixed_domain_doc(self):
        """A realistic doc with both data and policy sections."""
        doc = CanonicalDocument(source_system="test", source_uri="test://1", title="Test")
        structured = {
            "overview": "NPL reporting policy and data pipeline spec.",
            "business_rules": ["DPD > 90 days = Group 5"],
            "requirements": ["Report submitted by T+1"],
            "field_mapping": [{"field": "dpd", "type": "int", "source": "loan_master", "description": "Days past due"}],
            "data_sources": [{"name": "loan_master", "purpose": "Core loan data"}],
            "definitions": {"DPD": "Days Past Due"},
        }
        LLMNormalizer._inject_structured_blocks(doc, structured)
        # Should have: overview + rules + requirements + table + data_sources + definitions = 6 blocks
        assert len(doc.content_blocks) >= 6
        tables = [b for b in doc.content_blocks if isinstance(b, TableBlock)]
        assert len(tables) == 1


class TestLLMApplyEnrichment:
    """Test _apply_enrichment stores document_type in metadata."""

    def test_document_type_stored(self):
        normalizer = LLMNormalizer()
        doc = CanonicalDocument(source_system="test", source_uri="test://1", title="Test")
        normalizer._apply_enrichment(doc, {"document_type": "policy", "domains": ["compliance"]})
        assert doc.metadata["document_type"] == "policy"
        assert "compliance" in doc.tags

    def test_quality_dimensions_stored(self):
        normalizer = LLMNormalizer()
        doc = CanonicalDocument(source_system="test", source_uri="test://1", title="Test")
        dims = {"clarity": 0.8, "completeness": 0.7, "graph_readiness": 0.9}
        normalizer._apply_enrichment(doc, {"quality_dimensions": dims})
        assert doc.metadata["quality_dimensions"]["clarity"] == 0.8

    def test_document_signals_stored(self):
        normalizer = LLMNormalizer()
        doc = CanonicalDocument(source_system="test", source_uri="test://1", title="Test")
        signals = {"contains_rules": True, "contains_metrics": False}
        normalizer._apply_enrichment(doc, {"document_signals": signals})
        assert doc.metadata["document_signals"]["contains_rules"] is True


class TestLLMNewSections:
    """Test _inject_structured_blocks for new prompt sections."""

    def test_inject_salient_points(self):
        doc = CanonicalDocument(source_system="test", source_uri="test://1", title="Test")
        structured = {
            "salient_points": [
                {"priority": 1, "type": "rule", "statement": "DPD > 90 = Group 5", "why_it_matters": "NPL classification"}
            ]
        }
        LLMNormalizer._inject_structured_blocks(doc, structured)
        texts = [b.content for b in doc.content_blocks if isinstance(b, TextBlock)]
        assert any("Salient Points" in t and "DPD > 90" in t for t in texts)

    def test_inject_insights(self):
        doc = CanonicalDocument(source_system="test", source_uri="test://1", title="Test")
        structured = {
            "insights": [
                {"insight": "Pipeline has single point of failure", "basis": "Only one ETL job", "impact": "Risk of data loss"}
            ]
        }
        LLMNormalizer._inject_structured_blocks(doc, structured)
        texts = [b.content for b in doc.content_blocks if isinstance(b, TextBlock)]
        assert any("Insights" in t and "single point of failure" in t for t in texts)

    def test_inject_action_items(self):
        doc = CanonicalDocument(source_system="test", source_uri="test://1", title="Test")
        structured = {
            "action_items": [{"task": "Setup monitoring", "owner": "DevOps", "deadline": "Q2"}]
        }
        LLMNormalizer._inject_structured_blocks(doc, structured)
        texts = [b.content for b in doc.content_blocks if isinstance(b, TextBlock)]
        assert any("Action Items" in t and "Setup monitoring" in t for t in texts)

    def test_inject_risks_issues(self):
        doc = CanonicalDocument(source_system="test", source_uri="test://1", title="Test")
        structured = {"risks_issues": ["No backup for critical pipeline"]}
        LLMNormalizer._inject_structured_blocks(doc, structured)
        texts = [b.content for b in doc.content_blocks if isinstance(b, TextBlock)]
        assert any("Risks" in t and "No backup" in t for t in texts)

    def test_inject_metrics_kpis(self):
        doc = CanonicalDocument(source_system="test", source_uri="test://1", title="Test")
        structured = {
            "metrics_kpis": [{"name": "NPL Ratio", "formula": "NPL/Total Loans", "meaning": "Credit quality"}]
        }
        LLMNormalizer._inject_structured_blocks(doc, structured)
        texts = [b.content for b in doc.content_blocks if isinstance(b, TextBlock)]
        assert any("Metrics" in t and "NPL Ratio" in t for t in texts)

    def test_inject_components(self):
        doc = CanonicalDocument(source_system="test", source_uri="test://1", title="Test")
        structured = {"components": [{"name": "API Gateway", "role": "Traffic router"}]}
        LLMNormalizer._inject_structured_blocks(doc, structured)
        texts = [b.content for b in doc.content_blocks if isinstance(b, TextBlock)]
        assert any("Components" in t and "API Gateway" in t for t in texts)

    def test_inject_open_questions(self):
        doc = CanonicalDocument(source_system="test", source_uri="test://1", title="Test")
        structured = {"open_questions": ["What is the SLA for data refresh?"]}
        LLMNormalizer._inject_structured_blocks(doc, structured)
        texts = [b.content for b in doc.content_blocks if isinstance(b, TextBlock)]
        assert any("Open Questions" in t and "SLA" in t for t in texts)
