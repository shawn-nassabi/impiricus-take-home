# Chatbot agent implementation

- We want to have an agentic chatbot, using langchain's agent loop. Check https://docs.langchain.com/oss/python/langchain/agents for documentation
- For RAG, we need to integrate with our chromaDB hybrid retrieval setup (check rag/RAG_README.md , also check https://docs.langchain.com/oss/python/integrations/vectorstores/index#chroma for langchain integration)
- We want to create retrieval tools and provide it to the agent
- Have a tool to only retrieve data with source="CAB"
  - The CAB data tends to have more detailed class meeting times, professor details, etc...
- Have a tool to only retrieve data with source="bulletin"
  - The bulletin data tends to have just the title and description of courses
- Also, the response should be sent streaming

- We need to expose the chatbot through a simple /query API
  - API request structure:

```json
{
  "q": "question text/query",
  "department": "optional"
}
```

- API response needs to have:
  - The top-k retrieved courses (including the course code, title, department, similarity, source)
  - The generated response text
- Use server-sent events since we will be connecting this to a frontend, this will ensure the frontend receives properly formatted data so it can show responsive UI

Also have a /evaluate endpoint

- This would report latency and retrieval count

### Model choice

- For the LLM, we will use OpenAI GPT 4.1-mini
- I have created a .env file, I will provide an API key there under the env variable: OPENAI_API_KEY

### Additional requirements:

- Log all queries and response times
- No authentication needed
