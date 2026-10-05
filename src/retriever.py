import os
import glob

from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

load_dotenv()  # loads OPENAI_API_KEY from .env

DATA_DIR = "data"
DB_DIR = "chroma_store"


# 1. LOAD ---- read each company product text file
def load_transcripts():

    docs = []
    for path in glob.glob(f"{DATA_DIR}/*.txt"):
        lines = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # FAQ exports include an old chatbot prompt before the knowledge text.
                if not lines and line.startswith((
                    "Answer the question based on the context below.",
                    "store the username whenever user said and then when user ask ",
                    "below contents are in the form of question and answer on next line,",
                )):
                    continue
                lines.append(line)
        text = " ".join(lines)

        docs.append(Document(page_content=text, metadata={"source": os.path.basename(path)}))

    return docs


# 2. BUILD ---- chunk, embed once, and keep it on disk so we don't re-embed
def load_store():
    embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

    if os.path.exists(DB_DIR):
        return Chroma(persist_directory=DB_DIR, embedding_function=embeddings)

    docs = load_transcripts()

    chunks = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150,
    ).split_documents(docs)

    return Chroma.from_documents(chunks, embeddings, persist_directory=DB_DIR)


def build_retriever():
    return load_store().as_retriever(search_kwargs={"k": 5})


# 3. TRY IT ---- python src/retriever.py
if __name__ == "__main__":

    retriever = build_retriever()

    results = retriever.invoke("What is MoneySign?")
    
    for r in results:
        print(f"[{r.metadata['source']}] {r.page_content[:150]}...\n")
