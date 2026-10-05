"""Cache the existing reranker at image build time; no OpenAI call or re-indexing."""

from sentence_transformers import CrossEncoder
from src.reranker import CROSS_ENCODER

CrossEncoder(CROSS_ENCODER)
print("Existing cross-encoder cached for deployment.")
