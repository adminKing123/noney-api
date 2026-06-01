import time
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.messages import HumanMessage, AIMessage
from ai.base import BaseAI
from ..contextprovider import ContextProvider
from ..pricing import calculate_text
from config import CONFIG
from utils.google_citations import get_citations_from_grounding

class GeminiTextAI(BaseAI):
    MAPPINGS = CONFIG.AI_MAPPINGS

    def __init__(
        self,
        model_name,
        system_prompt=None,
        temperature=0.7,
        top_p=1.0,
        top_k=40,
    ):
        self.model_name = model_name
        self.details = self.MAPPINGS.get(model_name, {})
        self.model = ChatGoogleGenerativeAI(
            model=self.details.get("model_id"),
            temperature=self.details.get("temperature", temperature),
            top_p=self.details.get("top_p", top_p),
            top_k=self.details.get("top_k", top_k),
        )
        self.model = self.model.bind_tools([{"google_search": {}}, {"url_context": {}}]) 
        self.system_prompt = self.details.get("system_prompt", system_prompt)

    def stream(self, payload):
        start_time = time.time()
        user = payload.get("user", {})
        user_id = user.get("user_id", None)
        chat_id = payload.get("chat_id", None)
        prompt = payload.get("prompt", "")

        yield self._send_step("info", "Summarizing context")
        effective_system_prompt = self._build_system_prompt(payload)
        # Cache key uses the base system prompt so conversation history is
        # shared across requests regardless of output-mode extensions.
        ctx = ContextProvider.get(self.model_name, user_id, chat_id, self.system_prompt)
        context = ctx.build_context(prompt, files=payload.get("files", []), effective_system_prompt=effective_system_prompt)
        ai_response = ""
        yield self._start()

        started = False
        accumulated_input_tokens = 0
        accumulated_output_tokens = 0

        grounding_metadatas = []
        for chunk in self.model.stream(context):
            if chunk.response_metadata.get("grounding_metadata", False):
                grounding_metadatas.append(chunk.response_metadata["grounding_metadata"])

            # Accumulate usage across all chunks — prompt_token_count (input)
            # only appears on the last streaming chunk; candidates_token_count
            # (output) is a per-chunk delta on every chunk.
            um = getattr(chunk, "usage_metadata", None)
            if um:
                accumulated_input_tokens += um.get("input_tokens", 0)
                accumulated_output_tokens += um.get("output_tokens", 0)

            if not started:
                yield self._started()
                started = True

            if isinstance(chunk.content, list):
                for block in chunk.content:
                    if isinstance(block, dict) and "text" in block:
                        ai_response += block["text"]
                        yield self._text(block["text"])
            else:
                ai_response += str(chunk.content)
                yield self._text(str(chunk.content))

        ctx.append(AIMessage(content=ai_response))

        if grounding_metadatas:
            yield self._send_step("fetch_source_information", "Preparing Citations")
            for grounding_metadata in grounding_metadatas:
                if grounding_metadata.get("grounding_chunks", False):
                    yield self._source(get_citations_from_grounding(grounding_metadata["grounding_chunks"], grounding_metadata.get("grounding_supports", [])))

        # langchain-google-genai 3.x streaming omits prompt_token_count from
        # intermediate chunks; it only appears in the final summary chunk which
        # LangChain may skip when there is no text content.  Fall back to
        # Gemini's count_tokens API (free, exact) when streaming gives us 0.
        if accumulated_input_tokens == 0:
            try:
                accumulated_input_tokens = self.model.get_num_tokens_from_messages(context)
            except Exception:
                accumulated_input_tokens = 0

        # Emit token usage and cost after all content has been streamed
        if accumulated_input_tokens > 0 or accumulated_output_tokens > 0:
            gemini_model_id = self.details.get("model_id", "")
            usage_info = calculate_text(
                gemini_model_id,
                accumulated_input_tokens,
                accumulated_output_tokens,
            )
            yield self._send_usage(usage_info)

        end_time = time.time()
        duration = end_time - start_time
        yield self._send_duration(duration)
        yield self._end()

    def invoke(self, payload):
        prompt = payload.get("prompt", "")
        content_parts=[]
        if prompt:
            content_parts.append({
                "type": "text",
                "text": prompt
            })
        for file in payload.get("files", []):
            file_uri = file.get("genai_file", {}).get("uri", None)
            if file_uri:
                content_parts.append({
                    "type": "file",
                    "file_id": file_uri,
                    "mime_type": file.get("genai_file", {}).get("mime_type", None),
                })

        return self.model.invoke([HumanMessage(content=content_parts)])

    def with_structured_output(self, *args, **kwargs):
        return self.model.with_structured_output(*args, **kwargs)
