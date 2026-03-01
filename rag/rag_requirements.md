# Requirements for RAG and chatbot setup

### We have two datasets:

- data/cab_courses.json (this contains the data scraped from the Courses at Brown webpage)
- data/bulletin_courses.json (this contains data scraped from Brown's bulletin)
- When putting all the data into the vector database, we should have one consolidated index. We can combine the two datasets into one by normalizing the bulletin_courses.json to match the json structure of cab_courses.json and just assign the missing fields values to be null.
- Later when doing retrieval, we will filter based on source (CAB or bulletin) accordingly, so we can still search from a particular dataset if we need to

### Vector db

- We need to setup a vector DB using ChromaDB locally (docs, getting started: https://docs.trychroma.com/docs/overview/getting-started)

- We should have a way to load all the embeddings into the vector DB when launching the app

- We want to have hybrid search (combine semantic vector similarity search with keyword or fuzzy text matching)

- For semantic/dense embedding, we can use mixbread-ai/mxbai-embed-large-v1 (https://huggingface.co/mixedbread-ai/mxbai-embed-large-v1)
  - Here is an example for how to use this embedding model:

```python

from sentence_transformers import SentenceTransformer

model = SentenceTransformer("mixedbread-ai/mxbai-embed-large-v1")

sentences = [
    "The weather is lovely today.",
    "It's so sunny outside!",
    "He drove to the stadium."
]
embeddings = model.encode(sentences)

similarities = model.similarity(embeddings, embeddings)
print(similarities.shape)
# [3, 3]
```

- Allow filtering with metadata
  - We need to allow metadata filtering
  - For example, we could filter queries by department, or from a specific professor, etc...

- Metadata & Scoring: Store and return the retrieved items with their similarity scores, source labels, and any other metadata needed for ranking or display.

### Scope of this implementation

- For now, we want to focus on setting up the vector database with hybrid search capability, keeping in mind that we will later integrate this into an agentic chatbot with langchain

- We don't need to implement the full chatbot yet, just focus on the data ingestion, embedding, vector db setup, etc...
