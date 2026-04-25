import os
import streamlit as st

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

from langchain_google_genai import GoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────


GOOGLE_API_KEY = os.environ.get("GEMINI_API_KEY")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHROMA_PATH = os.path.join(BASE_DIR, "chroma_db")

# ─────────────────────────────────────────────
# LOAD + SPLIT DOCS
# ─────────────────────────────────────────────
def load_and_split_docs():
    loader1 = PyPDFLoader(os.path.join(BASE_DIR, "assets/canine-vaccination-chart.pdf"))
    loader2 = PyPDFLoader(os.path.join(BASE_DIR, "assets/pet_safety_vaccination_guide.pdf"))

    docs = loader1.load() + loader2.load()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100
    )

    return splitter.split_documents(docs)

# ─────────────────────────────────────────────
# EMBEDDINGS (LOCAL — NO API ISSUES)
# ─────────────────────────────────────────────
def get_embeddings():
    return HuggingFaceEmbeddings(
        model_name="all-MiniLM-L6-v2"
    )

# ─────────────────────────────────────────────
# CHROMA VECTORSTORE (PERSISTENT)
# ─────────────────────────────────────────────
@st.cache_resource
def init_vectorstore():
    embeddings = get_embeddings()

    # Load existing DB if it exists
    if os.path.exists(CHROMA_PATH):
        return Chroma(
            persist_directory=CHROMA_PATH,
            embedding_function=embeddings
        )

    # Otherwise build it
    docs = load_and_split_docs()

    vectorstore = Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        persist_directory=CHROMA_PATH
    )

    vectorstore.persist()
    return vectorstore

# ─────────────────────────────────────────────
# LLM CHAIN
# ─────────────────────────────────────────────
def build_chain():
    prompt = PromptTemplate.from_template("""
You are PawPal+, an intelligent pet care assistant embedded in a \
scheduling and care management app.
Your primary role is to answer pet health and safety questions to help pet owners make \
informed care decisions. You are given context from two documents: a canine vaccination \
chart and a pet safety & vaccination community guide.

You can help with:
- Dog and cat vaccination schedules and timing (by age)
- Core vs. non-core vaccine distinctions
- Boarding vaccination requirements (DHPP, Bordetella, Rabies)
- Common pet hazards: toxic foods, plants, and household chemicals
- Emergency contacts (e.g., ASPCA Poison Control: 888-426-4435)
- General guidance on when to contact a vet

You are part of a larger app that also helps owners schedule daily pet care tasks, track \
medications, and coordinate with care providers. If a user asks about scheduling, tasks, \
or app features, let them know that functionality is available in the main dashboard.

Keep responses friendly, concise, and accessible to everyday pet owners — not veterinary \
professionals. Always recommend consulting a licensed vet for personalized medical decisions.

Only answer based on the context provided. If the answer is not in the provided documents, \
say so honestly.

Context:
{context}

Question:
{question}
""")

    model = GoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=GOOGLE_API_KEY,
        temperature=0
    )

    return prompt | model | StrOutputParser()

# ─────────────────────────────────────────────
# RAG QUERY FUNCTION
# ─────────────────────────────────────────────
import numpy as np

def ask_rag(question, vectorstore):
    retriever = vectorstore.as_retriever(search_kwargs={"k": 4})

    docs = retriever.invoke(question)  # Fix 2: was get_relevant_documents()

    if not docs:
        return {"answer": "I couldn't find that information in the provided documents.", "confidence": 0.0}

    context = "\n\n".join([d.page_content for d in docs])

    try:
        scores = vectorstore.similarity_search_with_score(question, k=4)
        similarities = [1 / (1 + score) for _, score in scores]  # Fix 1: was 1 - score
        confidence = float(np.mean(similarities))
    except:
        confidence = 0.5

    chain = build_chain()
    answer = chain.invoke({"context": context, "question": question})
    return {"answer": answer, "confidence": round(confidence, 2)}

def run_basic_checks(vectorstore):
    tests_passed = 0

    # Test 1: retrieval works
    docs = vectorstore.similarity_search("rabies vaccine", k=2)
    if docs:
        tests_passed += 1

    # Test 2: empty query
    try:
        res = ask_rag("", vectorstore)
        if res["answer"]:
            tests_passed += 1
    except:
        pass

    # Test 3: unknown query handled
    res = ask_rag("quantum physics for cats", vectorstore)
    if "couldn’t find" in res["answer"].lower():
        tests_passed += 1

    return tests_passed

# ─────────────────────────────────────────────
# INIT STORE
# ─────────────────────────────────────────────
vectorstore = init_vectorstore()

# optional test (if running file directly)
if __name__ == "__main__":
    print("Chroma RAG ready.")
    print(f"Tests passed: {run_basic_checks(vectorstore)}/3")