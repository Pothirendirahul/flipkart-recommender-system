from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage, AIMessage
from flipkart.config import Config

class RAGChainBuilder:
    def __init__(self, vector_store):
        self.vector_store = vector_store
        self.model = ChatGroq(model=Config.RAG_MODEL, temperature=0.5)
        self.history_store = {}

    def _get_history(self, session_id: str):
        if session_id not in self.history_store:
            self.history_store[session_id] = []
        return self.history_store[session_id]

    def build_chain(self):
        retriever = self.vector_store.as_retriever(search_kwargs={"k": 3})

        prompt = ChatPromptTemplate.from_messages([
            ("system", """You're an e-commerce bot answering product-related queries using reviews and titles.
                          Stick to context. Be concise and helpful.\n\nCONTEXT:\n{context}"""),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}")
        ])

        def format_docs(docs):
            return "\n\n".join(doc.page_content for doc in docs)

        def route_query(inputs):
            """Route the query through retrieval and formatting"""
            query = inputs.get("input", "")
            docs = retriever.invoke(query)
            context = format_docs(docs)
            return {
                "context": context,
                "input": query,
                "chat_history": inputs.get("chat_history", [])
            }

        # Build the chain
        chain = (
            RunnableLambda(route_query)
            | prompt
            | self.model
            | StrOutputParser()
        )

        # Wrapper to handle history
        def invoke_with_history(inputs, session_id="default"):
            history = self._get_history(session_id)
            
            # Add history to inputs
            inputs_with_history = {
                **inputs,
                "chat_history": history
            }
            
            # Get response
            response = chain.invoke(inputs_with_history)
            
            # Update history
            history.append(HumanMessage(content=inputs["input"]))
            history.append(AIMessage(content=response))
            
            return {"answer": response}

        # Return a callable object
        class ChainWrapper:
            def __init__(self, func):
                self.func = func
            
            def invoke(self, inputs, config=None):
                session_id = "default"
                if config and "configurable" in config:
                    session_id = config["configurable"].get("session_id", "default")
                return self.func(inputs, session_id)
        
        return ChainWrapper(invoke_with_history)