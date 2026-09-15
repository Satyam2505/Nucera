import numpy as np

from app.services.embedding_service import EMBEDDING_DIM, embed_texts, generate_embedding


def test_generate_embedding_has_expected_dimension():
    vec = generate_embedding("Binary search trees are a data structure.")
    assert len(vec) == EMBEDDING_DIM


def test_embed_texts_batch_matches_input_count():
    vectors = embed_texts(["first chunk", "second chunk", "third chunk"])
    assert len(vectors) == 3
    assert all(len(v) == EMBEDDING_DIM for v in vectors)


def test_embed_texts_empty_list_returns_empty_list():
    assert embed_texts([]) == []


def test_semantically_similar_text_embeds_closer_than_unrelated_text():
    a = np.array(generate_embedding("Binary search trees are a hierarchical data structure."))
    b = np.array(generate_embedding("A binary search tree is a tree-based data structure."))
    c = np.array(generate_embedding("The stock market closed higher today after strong earnings."))

    sim_related = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
    sim_unrelated = np.dot(a, c) / (np.linalg.norm(a) * np.linalg.norm(c))

    assert sim_related > sim_unrelated
