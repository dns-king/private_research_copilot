from app.ingestion.chunking import Chunker, estimate_tokens


def test_sentence_chunking_respects_size():
    text = "Alpha beta gamma. " * 120
    chunks = Chunker(chunk_size=180, chunk_overlap=20, strategy="sentence").split(text)
    assert len(chunks) > 1
    assert all(chunk.text for chunk in chunks)
    assert all(chunk.token_count > 0 for chunk in chunks)


def test_token_chunking_has_overlap():
    text = " ".join(f"word{i}" for i in range(100))
    chunks = Chunker(chunk_size=100, chunk_overlap=25, strategy="token").split(text)
    assert len(chunks) > 1
    assert chunks[0].text.split()[-1] in chunks[1].text.split()


def test_estimate_tokens_never_zero():
    assert estimate_tokens("") == 1

