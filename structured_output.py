import re
import json
from typing import Dict, Any, List, Optional, Tuple

class StructuredOutputPipeline:
    """
    Structured Output Generation Pipeline.
    Transforms raw extracted document chunks into validated, typed,
    domain-specific structured academic data and user-friendly representations.
    
    Pipeline Stages:
    Input Chunks -> Content Analysis -> Schema Selection -> Structured Data Generation -> Validation -> UI Rendering
    """

    SUPPORTED_CONTENT_TYPES = [
        "conceptual_definition",
        "process_workflow",
        "architectural_system",
        "comparative_analysis"
    ]

    @classmethod
    def analyze_content(cls, question: str, context_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Stage 1: Content Analysis
        Analyzes the extracted context text and question to determine:
        - Domain category
        - Purpose and content type
        - Key entities and terminology
        - Sequential steps / operational stages
        - Component relationships and properties
        """
        combined_text = " ".join([c.get("text", "") for c in context_chunks])
        text_lower = combined_text.lower()
        q_lower = question.lower()

        # 1. Determine Content Type
        if any(w in q_lower for w in ["difference", "compare", "versus", "vs", "distinguish", "contrast"]):
            content_type = "comparative_analysis"
        elif any(w in q_lower for w in ["algorithm", "lifecycle", "transition", "steps", "workflow", "banker", "handshake", "phase", "procedure", "scheduling"]):
            content_type = "process_workflow"
        elif any(w in q_lower for w in ["architecture", "hardware", "layer", "layers", "mmu", "osi", "tcp", "paging", "structure", "subsystem"]):
            content_type = "architectural_system"
        else:
            content_type = "conceptual_definition"

        # 2. Identify Academic Domain
        domain = "Computer Science & Engineering"
        if any(w in text_lower for w in ["page", "mmu", "process", "deadlock", "scheduler", "kernel", "thread", "virtual memory"]):
            domain = "Operating Systems & Systems Programming"
        elif any(w in text_lower for w in ["layer", "protocol", "packet", "subnet", "ip", "tcp", "udp", "csma", "ethernet", "router"]):
            domain = "Computer Communication Networks"
        elif any(w in text_lower for w in ["database", "sql", "transaction", "acid", "relation", "table"]):
            domain = "Database Management Systems"

        # 3. Extract Key Technical Entities (acronyms, capitalized tech terms, domain keywords)
        entities = []
        # Find acronyms (2-6 uppercase letters)
        acronyms = list(set(re.findall(r'\b[A-Z]{2,6}\b', combined_text)))
        entities.extend(acronyms[:6])

        # Find significant technical multi-word terms
        tech_terms = [
            "Logical Address", "Physical Address", "Page Table", "Frame", "Memory Management Unit",
            "Long-Term Scheduler", "Short-Term Scheduler", "Context Switching", "Deadlock Avoidance",
            "Banker's Algorithm", "Safe State", "Resource Allocation", "Application Layer",
            "Transport Layer", "Network Layer", "Data Link Layer", "Physical Layer",
            "Three-Way Handshake", "CSMA/CD", "Subnet Mask", "IP Addressing"
        ]
        for term in tech_terms:
            if term.lower() in text_lower and term not in entities:
                entities.append(term)

        # 4. Extract Relationships (e.g., A maps to B, A delivers to B, A transitions to B)
        relationships = []
        rel_patterns = [
            (r'([A-Za-z\s]{3,20})\s+(?:maps|translates)\s+(?:to|into)\s+([A-Za-z\s]{3,20})', 'maps to'),
            (r'([A-Za-z\s]{3,20})\s+(?:is divided into|consists of)\s+([A-Za-z\s]{3,30})', 'subdivides into'),
            (r'([A-Za-z\s]{3,20})\s+(?:provides|ensures)\s+([A-Za-z\s]{3,25})', 'provides'),
            (r'([A-Za-z\s]{3,20})\s+(?:dispatched to|transitions to)\s+([A-Za-z\s]{3,20})', 'transitions to')
        ]
        for pattern, rel_type in rel_patterns:
            matches = re.findall(pattern, combined_text, re.IGNORECASE)
            for m1, m2 in matches[:3]:
                relationships.append({
                    "source": m1.strip(),
                    "relation": rel_type,
                    "target": m2.strip()
                })

        # 5. Extract Sentences for fact grounding
        sentences = [s.strip() for s in re.split(r'(?<=[.?!])\s+', combined_text) if len(s.strip()) > 20]

        return {
            "content_type": content_type,
            "domain": domain,
            "entities": entities[:8],
            "relationships": relationships[:4],
            "sentences": sentences,
            "combined_text": combined_text
        }

    
    @classmethod
    def generate_structured_data(cls, question: str, marks: int,
                                 context_chunks: List[Dict[str, Any]],
                                 analysis: Optional[Dict[str, Any]] = None,
                                 target_points: Optional[int] = None) -> Dict[str, Any]:
        """
        Creates structured academic content using only facts extracted
        from the supplied PDF context. Does not insert predefined examples
        or unsupported technical details.
        """
        if analysis is None:
            analysis = cls.analyze_content(question, context_chunks)

        if target_points is None:
            target_points = marks * 2

        topic = question.strip().rstrip("?").rstrip(".")
        content_type = analysis.get("content_type", "conceptual_definition")
        domain = analysis.get("domain", "Computer Science & Engineering")
        entities = analysis.get("entities", [])
        sentences = analysis.get("sentences", [])

        # Keep only sentences that contain at least one meaningful
        # question keyword.
        stop_words = {
            "what", "which", "where", "when", "explain", "describe",
            "discuss", "define", "state", "list", "with", "from",
            "that", "this", "their", "there", "does", "have",
            "about", "give", "write", "brief", "concept", "diagram"
        }

        keywords = {
            word for word in re.findall(r"\b[a-zA-Z]{3,}\b", question.lower())
            if word not in stop_words
        }

        relevant_sentences = []
        for sentence in sentences:
            sentence_lower = sentence.lower()
            if keywords and any(
                re.search(r"\b" + re.escape(word) + r"\b", sentence_lower)
                for word in keywords
            ):
                if sentence not in relevant_sentences:
                    relevant_sentences.append(sentence)

        # Do not create generic content when the PDF does not support it.
        sections = []
        missing_fields = []

        if not relevant_sentences:
            missing_fields.append(
                "No sufficiently relevant sentences were identified in the retrieved context."
            )

        # Use actual retrieved sentences as evidence.
        # No predefined component descriptions or fabricated steps.
        if relevant_sentences:
            sections.append({
                "heading": "Relevant Information from the PDF",
                "type": "bullet_points",
                "points": relevant_sentences[:target_points],
                "summary": "Information relevant to the question, extracted from the retrieved PDF context."
            })

        if entities:
            sections.append({
                "heading": "Key Technical Terms",
                "type": "bullet_points",
                "points": entities[:8],
                "summary": "Technical terms identified in the retrieved context."
            })

        structured_result = {
            "schema_version": "2.0",
            "topic": topic,
            "content_type": content_type,
            "domain": domain,
            "executive_summary": (
                relevant_sentences[0]
                if relevant_sentences
                else "Insufficient relevant information was identified in the retrieved PDF context."
            ),
            "key_entities": entities[:8],
            "sections": sections,
            "technical_attributes": {},
            "missing_or_uncertain_fields": missing_fields,
            "examiner_takeaways": [
                "Use only technical details supported by the uploaded document.",
                "Explain each relevant concept clearly in the examination."
            ],
            "required_points": target_points,
            "generated_points": len(relevant_sentences[:target_points])
        }

        return structured_result


    @classmethod
    def validate_structured_output(cls, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Stage 4: Validation
        Ensures the generated structured data adheres to required fields,
        valid data types, and logical organization.
        """
        errors = []
        if not isinstance(data, dict):
            return False, ["Root output is not a dictionary"]

        required_keys = ["schema_version", "topic", "content_type", "domain", "sections"]
        for k in required_keys:
            if k not in data or not data[k]:
                errors.append(f"Missing or empty required top-level field: '{k}'")

        if data.get("content_type") not in cls.SUPPORTED_CONTENT_TYPES:
            errors.append(f"Invalid content_type: '{data.get('content_type')}'. Supported: {cls.SUPPORTED_CONTENT_TYPES}")

        sections = data.get("sections", [])
        if not isinstance(sections, list) or len(sections) == 0:
            errors.append("Sections field must be a non-empty list of structured section objects.")
        else:
            for idx, sec in enumerate(sections):
                if not isinstance(sec, dict):
                    errors.append(f"Section {idx} is not a valid dictionary.")
                    continue
                if "heading" not in sec:
                    errors.append(f"Section {idx} is missing 'heading'.")
                if "type" not in sec:
                    errors.append(f"Section {idx} is missing 'type'.")

                stype = sec.get("type")
                if stype == "table":
                    tdata = sec.get("table_data", {})
                    if not isinstance(tdata, dict) or "headers" not in tdata or "rows" not in tdata:
                        errors.append(f"Section {idx} of type 'table' is missing valid table_data.")
                elif stype == "ordered_steps":
                    if not isinstance(sec.get("steps"), list):
                        errors.append(f"Section {idx} of type 'ordered_steps' is missing steps list.")
                elif stype == "key_value":
                    if not isinstance(sec.get("items"), list):
                        errors.append(f"Section {idx} of type 'key_value' is missing items list.")
                elif stype == "bullet_points":
                    if not isinstance(sec.get("points"), list):
                        errors.append(f"Section {idx} of type 'bullet_points' is missing points list.")

        # Warn (not fail) if required_points vs generated_points differ significantly
        warnings = []
        required = data.get("required_points")
        generated = data.get("generated_points")
        if required and generated and abs(required - generated) > required * 0.5:
            warnings.append(f"WARNING: Generated {generated} points but required {required} (marks × 2). Consider reviewing context coverage.")

        return len(errors) == 0, errors + warnings

    @classmethod
    def render_to_markdown(cls, structured_data: Dict[str, Any], marks: int) -> str:
        """
        Converts the validated structured data into cleanly formatted, mark-calibrated
        Markdown adhering strictly to the university exam structure.
        """
        target_points = structured_data.get("required_points", marks * 2)
        generated_points = structured_data.get("generated_points", target_points)
        topic = structured_data.get('topic', 'Academic Analysis')

        parts = []

        # Standard Exam Question & Marks Header
        parts.append(f"**Question:** {topic}\n")
        parts.append(f"**Marks:** {marks}\n")
        parts.append("**Answer:**\n")

        # Academic Overview
        if structured_data.get('executive_summary'):
            parts.append(f"> **Overview**: {structured_data.get('executive_summary')}\n")

        # Key entities chips
        if structured_data.get("key_entities"):
            chips = " • ".join([f"`{e}`" for e in structured_data["key_entities"][:6]])
            parts.append(f"🔑 **Key Entities & Symbols**: {chips}\n")

        # Sections
        point_idx = 1
        for sec in structured_data.get("sections", []):
            parts.append(f"### {sec.get('heading', 'Section')}")
            if sec.get("summary"):
                parts.append(f"*{sec['summary']}*\n")

            stype = sec.get("type")
            if stype == "key_value":
                for item in sec.get("items", []):
                    parts.append(f"{point_idx}. **{item['key']}**: {item['value']}")
                    point_idx += 1
                parts.append("")

            elif stype == "table":
                tdata = sec.get("table_data", {})
                headers = tdata.get("headers", [])
                rows = tdata.get("rows", [])
                if headers and rows:
                    parts.append("| " + " | ".join(headers) + " |")
                    parts.append("| " + " | ".join(["---"] * len(headers)) + " |")
                    for r in rows:
                        parts.append("| " + " | ".join([str(cell).replace("|", "/") for cell in r]) + " |")
                    parts.append("")

            elif stype == "ordered_steps":
                for s in sec.get("steps", []):
                    parts.append(f"**Step {s.get('step_number', point_idx)}: {s.get('phase_name', 'Phase')}**")
                    parts.append(f"- *Action*: {s.get('action', '')}")
                    parts.append(f"- *Resulting State*: `{s.get('resulting_state', '')}`\n")
                    point_idx += 1

            elif stype == "bullet_points":
                for pt in sec.get("points", []):
                    parts.append(f"{point_idx}. {pt}")
                    point_idx += 1
                parts.append("")

        parts.append(f"📌 **Points Generated:** {generated_points} / {target_points} required ({marks} marks × 2)")
        return "\n".join(parts)
