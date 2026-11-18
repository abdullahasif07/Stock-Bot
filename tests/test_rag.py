from backend.rag.chunking import chunk_document, split_into_sections
from backend.rag.index import DocumentIndex, tokenize

SAMPLE_10K = """UNITED STATES SECURITIES AND EXCHANGE COMMISSION
FORM 10-K
Item 1. Business 3
Item 1A. Risk Factors 9
PART I
Item 1. Business
We sell cloud computing services and consumer electronics worldwide. Our cloud segment is called NimbusCloud.
We employed approximately 12,000 full-time employees as of December 31, 2025.
Item 1A. Risk Factors
Competition in cloud computing is intense and could reduce our margins.
Supply chain disruptions in Asia could delay shipments of our devices.
Item 7. Management's Discussion and Analysis
Net sales | 2025 | 2024
NimbusCloud | 45,100 | 38,200
Devices | 20,500 | 21,900
Total net sales increased 12% driven by NimbusCloud growth.
"""


def test_sections_skip_table_of_contents():
    labels = [s for s, _ in split_into_sections(SAMPLE_10K)]
    assert labels == ["Cover / Overview", "Item 1. Business", "Item 1A. Risk Factors",
                      "Item 7. Management's Discussion and Analysis"]


def test_chunks_respect_size_and_keep_overlap():
    text = "Item 7. MD&A\n" + "\n".join(f"Sentence number {i} about revenue and margins." for i in range(400))
    chunks = chunk_document(text, size=500, overlap=100)
    assert len(chunks) > 10
    assert all(len(c.text) <= 600 for c in chunks)
    assert all(c.section == "Item 7. MD&A" for c in chunks)
    # consecutive chunks share overlapping lines
    assert chunks[0].text.splitlines()[-1] in chunks[1].text


def test_long_single_line_is_split():
    chunks = chunk_document("word " * 2000, size=800, overlap=0)
    assert len(chunks) >= 10 and all(len(c.text) <= 800 for c in chunks)


def test_tokenize_keeps_numbers():
    assert tokenize("Net sales were $45,100 in 2025") == ["net", "sales", "45,100", "2025"]


def test_hybrid_search_finds_relevant_sections(tmp_path):
    chunks = chunk_document(SAMPLE_10K, size=200, overlap=0)
    idx = DocumentIndex.build("TEST_1", {"title": "Test 10-K"}, chunks)

    top = idx.search("What are the risk factors around competition?", k=2)
    assert any("Competition" in c.text for c, _ in top)

    top = idx.search("NimbusCloud net sales 2025", k=2)
    assert any("45,100" in c.text for c, _ in top)

    idx.save(str(tmp_path))
    loaded = DocumentIndex.load(str(tmp_path), "TEST_1")
    assert loaded and len(loaded.chunks) == len(chunks)
    assert loaded.search("employees", k=1)[0][0].text == idx.search("employees", k=1)[0][0].text
