"""Deterministic RAG evaluation dataset for the Nova Institute demo
knowledge base (Task 005 section 61). Each entry pairs a representative
student question with whether the seeded knowledge should be able to
answer it reliably.
"""
from __future__ import annotations

NOVA_KNOWLEDGE_TEXT = """
Nova Institute of Technology Admission Handbook 2026-27

Courses Offered
Nova Institute of Technology offers the following programs: B.Tech Computer
Science and Engineering, B.Tech Artificial Intelligence and Machine Learning,
Bachelor of Computer Applications, Master of Business Administration, and
Master of Computer Applications.

Admission Process
Applicants apply online through the admissions portal, appear for the
required entrance counseling session where applicable, submit supporting
documents, and pay the admission fee to confirm their seat.

Required Documents
Applicants should keep the following documents ready: Class 10 marksheet,
Class 12 marksheet, a government-issued photo ID, passport-size photographs,
and an entrance exam scorecard where applicable.

Scholarships
Nova Institute of Technology offers merit-based scholarships to
high-scoring admitted students, subject to seat availability and
verification of academic records.

Hostel Information
On-campus hostel accommodation is available for most programs. Hostel fees
are listed alongside each course's fee structure. Rooms are allocated on a
first-come, first-served basis during the admission cycle.

Placements
The placement cell works with recruiters across the software, product, and
analytics sectors. Recent batches have seen participation from a growing
number of technology recruiters.
"""

EVAL_QUESTIONS: list[tuple[str, bool]] = [
    ("What courses are offered at Nova Institute?", True),
    ("What documents are required for admission?", True),
    ("What is the admission process?", True),
    ("What scholarships are available?", True),
    ("Tell me about hostel facilities.", True),
    ("Tell me about placements.", True),
    ("Do you offer a scholarship for underwater basket weaving?", False),
    ("What is the capital of France?", False),
]
