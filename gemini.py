import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import AIMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda
from langchain_google_genai import GoogleGenerativeAI

# ── Config ────────────────────────────────────────────────────────────────────
GOOGLE_API_KEY = os.environ.get("GEMINI_API_KEY")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Load PDFs ─────────────────────────────────────────────────────────────────
loader  = PyPDFLoader(os.path.join(BASE_DIR, "assets/canine-vaccination-chart.pdf"))
loader2 = PyPDFLoader(os.path.join(BASE_DIR, "assets/pet_safety_vaccination_guide.pdf"))
docs = loader.load() + loader2.load()

tables = []
texts  = [d.page_content for d in docs]

# ── Summarization ─────────────────────────────────────────────────────────────
def generate_text_summaries(texts, tables, summarize_texts=False):
    """
    Summarize text elements.
    texts:           List of str
    tables:          List of str
    summarize_texts: Bool to summarize texts
    """
    prompt_text = """You are PawPal+, an intelligent pet care assistant embedded in a \
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

You are an assistant tasked with summarizing tables and text for retrieval. \
These summaries will be embedded and used to retrieve the raw text or table elements. \
Give a concise summary of the table or text that is well optimized for retrieval.

Table or text: {element}"""

    prompt = PromptTemplate.from_template(prompt_text)

    empty_response = RunnableLambda(
        lambda x: AIMessage(content="Error processing document")
    )

    model = GoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=GOOGLE_API_KEY,
        temperature=0,
        max_output_tokens=1024,
    )

    summarize_chain = {"element": lambda x: x} | prompt | model | StrOutputParser()

    text_summaries  = []
    table_summaries = []

    if texts and summarize_texts:
        text_summaries = summarize_chain.batch(texts, {"max_concurrency": 1})
    elif texts:
        text_summaries = texts

    if tables:
        table_summaries = summarize_chain.batch(tables, {"max_concurrency": 1})

    return text_summaries, table_summaries


# ── Run ───────────────────────────────────────────────────────────────────────
text_summaries, table_summaries = generate_text_summaries(
    texts, tables, summarize_texts=True
)

print("=== Summary of page 1 ===")
print(text_summaries[0])
print("\n=== Summary of page 2 ===")
print(text_summaries[1])
print(f"\nTotal summaries generated: {len(text_summaries)}")