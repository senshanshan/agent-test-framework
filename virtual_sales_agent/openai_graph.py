import os
from datetime import datetime
from typing import Annotated

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import AnyMessage, add_messages
from langgraph.prebuilt import tools_condition
from typing_extensions import TypedDict

from virtual_sales_agent.tools import (
    check_order_status,
    create_order,
    get_available_categories,
    search_products,
    search_products_recommendations,
)
from virtual_sales_agent.utils import create_tool_node_with_fallback


load_dotenv()


class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    user_info: str


class Assistant:
    def __init__(self, runnable: Runnable):
        self.runnable = runnable

    def __call__(self, state: State, config: RunnableConfig):
        while True:
            configuration = config.get("configurable", {})
            customer_id = configuration.get("customer_id", None)
            state = {**state, "user_info": customer_id}
            result = self.runnable.invoke(state)
            if not result.tool_calls and (
                not result.content
                or isinstance(result.content, list)
                and not result.content[0].get("text")
            ):
                messages = state["messages"] + [("user", "Respond with a real output.")]
                state = {**state, "messages": messages}
            else:
                break
        return {"messages": result}


safe_tools = [
    get_available_categories,
    search_products,
    search_products_recommendations,
    check_order_status,
]
sensitive_tools = [create_order]
sensitive_tool_names = {tool.name for tool in sensitive_tools}


assistant_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a helpful virtual sales assistant for an online store.

Your job is to help customers find products, check inventory and prices, place orders, and track order status.
Use tools whenever the answer depends on product, inventory, recommendation, or order data.

Important rules:
- Do not invent product, inventory, price, customer, or order information.
- If the user asks about available products, categories, prices, recommendations, or orders, call the relevant tool.
- For order status, only use the current customer's data.
- For order creation, verify product availability and let the sensitive tool flow request approval.
- If the user asks for another customer's order, refuse.
- Keep answers concise and useful.

Current customer id:
{user_info}

Current time: {time}.""",
        ),
        ("placeholder", "{messages}"),
    ]
).partial(time=datetime.now)


agent_mode = os.getenv("AGENT_MODE", "openai").lower()

if agent_mode == "doubao":
    api_key = os.getenv("DOUBAO_API_KEY") or os.getenv("ARK_API_KEY")
    base_url = os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    model = os.getenv("DOUBAO_ENDPOINT_ID") or os.getenv("DOUBAO_MODEL")
else:
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL") or None
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

if not api_key:
    raise ValueError(
        "Missing API key. Set OPENAI_API_KEY for AGENT_MODE=openai, "
        "or DOUBAO_API_KEY/ARK_API_KEY for AGENT_MODE=doubao."
    )

if not model:
    raise ValueError(
        "Missing model. Set OPENAI_MODEL for AGENT_MODE=openai, "
        "or DOUBAO_ENDPOINT_ID for AGENT_MODE=doubao."
    )

llm = ChatOpenAI(
    model=model,
    temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.2")),
    api_key=api_key,
    base_url=base_url,
)

assistant_runnable = assistant_prompt | llm.bind_tools(safe_tools + sensitive_tools)

builder = StateGraph(State)
builder.add_node("assistant", Assistant(assistant_runnable))
builder.add_node("safe_tools", create_tool_node_with_fallback(safe_tools))
builder.add_node("sensitive_tools", create_tool_node_with_fallback(sensitive_tools))


def route_tools(state: State):
    next_node = tools_condition(state)
    if next_node == END:
        return END
    ai_message = state["messages"][-1]
    first_tool_call = ai_message.tool_calls[0]
    if first_tool_call["name"] in sensitive_tool_names:
        return "sensitive_tools"
    return "safe_tools"


builder.add_edge(START, "assistant")
builder.add_conditional_edges(
    "assistant", route_tools, ["safe_tools", "sensitive_tools", END]
)
builder.add_edge("safe_tools", "assistant")
builder.add_edge("sensitive_tools", "assistant")

memory = MemorySaver()
graph = builder.compile(checkpointer=memory, interrupt_before=["sensitive_tools"])
