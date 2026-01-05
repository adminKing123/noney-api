import time
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.messages import AIMessage, AIMessageChunk, ToolMessage
from ai.base import BaseAI
from langchain.agents import create_agent
from .tools import tools
from ..contextprovider import ContextProvider
from config import CONFIG
import json

class HrmsPreviewAI(BaseAI):
    MAPPINGS = CONFIG.AI_MAPPINGS

    def __init__(
        self,
        model_name,
        system_prompt=None,
        temperature=None,
        top_p=None,
        top_k=None,
    ):
        self.model_name = model_name
        self.details = self.MAPPINGS.get(model_name, {})
        self.model = ChatGoogleGenerativeAI(
            model=self.details.get("model_id"),
            temperature=self.details.get("temperature", temperature),
            top_p=self.details.get("top_p", top_p),
            top_k=self.details.get("top_k", top_k),
        )
        self.system_prompt = self.details.get("system_prompt", system_prompt)
        self.agent = create_agent(
            model=self.model,
            tools=tools,
            system_prompt=self.system_prompt,
        )

    def stream(self, payload):
        start_time = time.time()
        user = payload.get("user", {})
        user_id = user.get("user_id", None)
        chat_uid = payload.get("chat_uid", None)
        prompt = payload.get("prompt", "")

        yield self._send_step("info", "Summarizing context")
        ctx = ContextProvider.get(self.model_name, user_id, chat_uid, self.system_prompt)
        context = ctx.build_context(prompt)

        ai_response = ""
        yield self._start()

        started = False

        index = 0
        for mode, chunk in self.agent.stream(
            {"messages": context},
            stream_mode=["updates", "messages"],
            context={ "user_id": user_id, "chat_uid": chat_uid},
        ):
            if mode == "messages":
                msg, meta = chunk
                if isinstance(msg, AIMessageChunk):
                    fc = msg.additional_kwargs.get("function_call")
                    if fc:
                        tool_name = fc["name"]
                        tool_args = fc["arguments"]
                        yield self._tool_call(tool_name, tool_args)


                if isinstance(msg, ToolMessage):
                    # ctx.append(ToolMessage(name=msg.name, content=msg.content, tool_call_id=msg.tool_call_id))
                    yield self._tool_result(msg.tool_call_id, msg.name, msg.content)


                if isinstance(msg, AIMessageChunk) and msg.content:
                    if (not started):
                        yield self._started()
                        started = True
                    if isinstance(msg.content, list):
                        for part in msg.content:
                            if type(part) == str:
                                ai_response += part
                                yield self._text(part, index=index)
                            elif part.get("type") == "text":
                                ai_response += part["text"]
                                yield self._text(part["text"], index=index)
                    else:
                        ai_response += msg.content
                        yield self._text(msg.content, index=index)

        ctx.append(AIMessage(content=ai_response))
        end_time = time.time()
        duration = end_time - start_time
        yield self._send_duration(duration)
        yield self._end()

    def invoke(self, payload):
        prompt = payload.get("prompt", "")
        return prompt
